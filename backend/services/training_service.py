"""Training service — real PyTorch training loops with progress tracking."""

import asyncio
import os
import time
import json
import traceback
from datetime import datetime, timezone
from typing import Optional

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
import torchvision
import torchvision.transforms as transforms
import torchvision.models as models

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
os.makedirs(MODEL_STORE, exist_ok=True)

# Global registry of active training tasks for cancellation
_active_jobs: dict[int, bool] = {}  # job_id -> should_stop


def get_device() -> torch.device:
    """Get best available device."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    try:
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return torch.device("xpu")
    except Exception:
        pass
    return torch.device("cpu")


def get_dataset(name: str, train: bool = True):
    """Load a torchvision dataset by name."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "datasets")
    os.makedirs(data_dir, exist_ok=True)

    if name == "mnist":
        transform = transforms.Compose([
            transforms.Grayscale(num_output_channels=3),
            transforms.Resize((32, 32)),
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,)),
        ])
        return torchvision.datasets.MNIST(root=data_dir, train=train, download=True, transform=transform)

    elif name == "fashion_mnist":
        transform = transforms.Compose([
            transforms.Grayscale(num_output_channels=3),
            transforms.Resize((32, 32)),
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,)),
        ])
        return torchvision.datasets.FashionMNIST(root=data_dir, train=train, download=True, transform=transform)

    elif name == "cifar10":
        transform_train = transforms.Compose([
            transforms.RandomHorizontalFlip(),
            transforms.RandomCrop(32, padding=4),
            transforms.ToTensor(),
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)),
        ])
        transform_test = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)),
        ])
        return torchvision.datasets.CIFAR10(
            root=data_dir, train=train, download=True,
            transform=transform_train if train else transform_test
        )
    else:
        raise ValueError(f"Unknown dataset: {name}. Supported: mnist, fashion_mnist, cifar10")


class SimpleCNN(nn.Module):
    """A simple CNN for small image classification tasks."""

    def __init__(self, num_classes: int = 10):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        self.classifier = nn.Sequential(
            nn.Linear(128 * 4 * 4, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = self.classifier(x)
        return x


def get_model(architecture: str, num_classes: int = 10) -> nn.Module:
    """Instantiate a model by architecture name."""
    if architecture == "simple_cnn":
        return SimpleCNN(num_classes=num_classes)
    elif architecture == "resnet18":
        model = models.resnet18(weights=None, num_classes=num_classes)
        return model
    elif architecture == "mobilenet_v2":
        model = models.mobilenet_v2(weights=None, num_classes=num_classes)
        return model
    elif architecture == "efficientnet_b0":
        model = models.efficientnet_b0(weights=None, num_classes=num_classes)
        return model
    else:
        raise ValueError(f"Unknown architecture: {architecture}. Supported: simple_cnn, resnet18, mobilenet_v2, efficientnet_b0")


def export_to_onnx(model: nn.Module, save_path: str, input_shape=(1, 3, 32, 32)):
    """Export a PyTorch model to ONNX format."""
    model.eval()
    dummy_input = torch.randn(*input_shape)
    torch.onnx.export(
        model,
        dummy_input,
        save_path,
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
    )


async def run_training(
    job_id: int,
    architecture: str,
    dataset_name: str,
    epochs: int = 10,
    batch_size: int = 64,
    learning_rate: float = 0.001,
    optimizer_name: str = "adam",
    weight_decay: float = 1e-4,
    db_session_factory=None,
    broadcast_fn=None,
):
    """
    Run a real PyTorch training loop.
    
    Updates the database with progress and broadcasts via WebSocket.
    Returns the path to the exported ONNX model on success.
    """
    _active_jobs[job_id] = False  # not stopped
    device = get_device()
    metrics_history = []

    def update_db(**kwargs):
        if db_session_factory is None:
            return
        db = db_session_factory()
        try:
            from database import TrainingJob
            job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            if job:
                for k, v in kwargs.items():
                    setattr(job, k, v)
                db.commit()
        finally:
            db.close()

    async def broadcast(data: dict):
        if broadcast_fn:
            await broadcast_fn(job_id, data)

    try:
        update_db(status="running", started_at=datetime.now(timezone.utc))
        await broadcast({"type": "status", "status": "running", "message": f"Starting training on {device}"})

        # Load dataset
        await broadcast({"type": "log", "message": f"Loading dataset: {dataset_name}..."})
        train_dataset = get_dataset(dataset_name, train=True)
        val_dataset = get_dataset(dataset_name, train=False)
        num_classes = len(train_dataset.classes) if hasattr(train_dataset, "classes") else 10

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0, pin_memory=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=True)
        await broadcast({"type": "log", "message": f"Dataset loaded: {len(train_dataset)} train, {len(val_dataset)} val samples"})

        # Build model
        await broadcast({"type": "log", "message": f"Building model: {architecture}..."})
        model = get_model(architecture, num_classes=num_classes).to(device)
        total_params = sum(p.numel() for p in model.parameters())
        await broadcast({"type": "log", "message": f"Model built: {total_params:,} parameters"})

        # Loss & optimizer
        criterion = nn.CrossEntropyLoss()
        if optimizer_name == "adam":
            opt = optim.Adam(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
        elif optimizer_name == "sgd":
            opt = optim.SGD(model.parameters(), lr=learning_rate, momentum=0.9, weight_decay=weight_decay)
        elif optimizer_name == "adamw":
            opt = optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
        else:
            opt = optim.Adam(model.parameters(), lr=learning_rate)

        scheduler = optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

        # Training loop
        for epoch in range(1, epochs + 1):
            if _active_jobs.get(job_id, False):
                update_db(status="stopped")
                await broadcast({"type": "status", "status": "stopped", "message": "Training stopped by user"})
                return None

            model.train()
            running_loss = 0.0
            correct = 0
            total = 0
            epoch_start = time.time()

            for batch_idx, (inputs, targets) in enumerate(train_loader):
                if _active_jobs.get(job_id, False):
                    break

                inputs, targets = inputs.to(device), targets.to(device)
                opt.zero_grad()
                outputs = model(inputs)
                loss = criterion(outputs, targets)
                loss.backward()
                opt.step()

                running_loss += loss.item()
                _, predicted = outputs.max(1)
                total += targets.size(0)
                correct += predicted.eq(targets).sum().item()

                # Send batch-level progress every 20 batches
                if (batch_idx + 1) % 20 == 0:
                    await broadcast({
                        "type": "batch_progress",
                        "epoch": epoch,
                        "batch": batch_idx + 1,
                        "total_batches": len(train_loader),
                        "loss": running_loss / (batch_idx + 1),
                        "accuracy": 100.0 * correct / total,
                    })
                    # Yield control to event loop
                    await asyncio.sleep(0)

            train_loss = running_loss / len(train_loader)
            train_acc = 100.0 * correct / total

            # Validation
            model.eval()
            val_loss = 0.0
            val_correct = 0
            val_total = 0
            with torch.no_grad():
                for inputs, targets in val_loader:
                    inputs, targets = inputs.to(device), targets.to(device)
                    outputs = model(inputs)
                    loss = criterion(outputs, targets)
                    val_loss += loss.item()
                    _, predicted = outputs.max(1)
                    val_total += targets.size(0)
                    val_correct += predicted.eq(targets).sum().item()

            val_loss /= len(val_loader)
            val_acc = 100.0 * val_correct / val_total
            epoch_time = time.time() - epoch_start

            scheduler.step()

            epoch_metrics = {
                "epoch": epoch,
                "train_loss": round(train_loss, 4),
                "train_accuracy": round(train_acc, 2),
                "val_loss": round(val_loss, 4),
                "val_accuracy": round(val_acc, 2),
                "epoch_time": round(epoch_time, 2),
                "lr": round(scheduler.get_last_lr()[0], 6),
            }
            metrics_history.append(epoch_metrics)

            update_db(
                current_epoch=epoch,
                train_loss=train_loss,
                train_accuracy=train_acc,
                val_loss=val_loss,
                val_accuracy=val_acc,
                metrics_history=metrics_history,
            )

            await broadcast({
                "type": "epoch_complete",
                **epoch_metrics,
                "total_epochs": epochs,
            })

        # Export to ONNX
        model_filename = f"train_{job_id}_{architecture}_{dataset_name}.onnx"
        onnx_path = os.path.join(MODEL_STORE, model_filename)
        await broadcast({"type": "log", "message": "Exporting model to ONNX format..."})
        export_to_onnx(model, onnx_path)

        # Also save PyTorch checkpoint
        pt_filename = f"train_{job_id}_{architecture}_{dataset_name}.pt"
        pt_path = os.path.join(MODEL_STORE, pt_filename)
        torch.save({
            "model_state_dict": model.state_dict(),
            "architecture": architecture,
            "num_classes": num_classes,
            "dataset": dataset_name,
            "metrics": metrics_history,
        }, pt_path)

        file_size = os.path.getsize(onnx_path)
        update_db(
            status="completed",
            completed_at=datetime.now(timezone.utc),
            metrics_history=metrics_history,
        )

        await broadcast({
            "type": "status",
            "status": "completed",
            "message": f"Training complete! Model exported to ONNX ({file_size / 1024 / 1024:.1f} MB)",
            "onnx_path": onnx_path,
            "pt_path": pt_path,
        })

        return {
            "onnx_path": onnx_path,
            "pt_path": pt_path,
            "file_size": file_size,
            "metrics": metrics_history,
        }

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        update_db(status="failed", error_message=error_msg)
        await broadcast({"type": "status", "status": "failed", "message": str(e)})
        raise
    finally:
        _active_jobs.pop(job_id, None)


def stop_training(job_id: int):
    """Signal a training job to stop."""
    if job_id in _active_jobs:
        _active_jobs[job_id] = True
        return True
    return False
