# Move sensitive files to internal/
$repo = "J:\NPU-STACK"
$internal = "$repo\internal"

# Root-level sensitive files
@(
    "Proposal - Intellify.txt",
    "HOW TO TRAIN PROPERLY IN NPU-STACK",
    "Unification-merger-absorbtion-Plan.MD",
    "Fleet MCP - OTA - REMOTE BOOT - MGMT - SERVICE AND DEVICE DISOVERY.md",
    "hardware_results.json",
    "renamed-persistence-session.json",
    "temp_prune_0kb.py",
    "temp_prune_action.py",
    "temp_prune_scanner.py",
    "test_hardware.py",
    "test_escape.bat",
    "test_quote.bat",
    "Torch 2.9.1+cu130 (default).bat",
    "model2GGUF.bat",
    "setup-edge-fleet.bat",
    "Long-Paths-Enabler.bat",
    "Set-MellanoxPriority.ps1"
) | ForEach-Object {
    $src = "$repo\$_"
    if (Test-Path $src) {
        Move-Item $src "$internal\" -Force
        Write-Host "MOVED: $_"
    } else {
        Write-Host "SKIP: $_ (not found)"
    }
}

# Training datasets
Get-ChildItem "$repo\datasets\*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
    Move-Item $_.FullName "$internal\datasets\" -Force
    Write-Host "MOVED: datasets/$($_.Name)"
}

# Dataset images and magneto
if (Test-Path "$repo\datasets\images") {
    Get-ChildItem "$repo\datasets\images" -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Replace("$repo\datasets\", "")
        $dest = "$internal\datasets\$rel"
        $destDir = Split-Path $dest -Parent
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
        Move-Item $_.FullName $dest -Force
    }
    Write-Host "MOVED: datasets/images/"
}
if (Test-Path "$repo\datasets\magneto") {
    robocopy "$repo\datasets\magneto" "$internal\datasets\magneto" /E /MOVE /NP /NFL /NDL
    Write-Host "MOVED: datasets/magneto/"
}

# Internal docs
@(
    "MOVING_FORWARD_DIRECTIVE.md",
    "PHASE-2-COMPLETION.md",
    "STATUS_REPORT_2026-05-28.md",
    "REPO_CLEANUP_MATRIX_2026-05-28.md",
    "UNIFIED-RUNTIME-COMPATIBILITY-ROADMAP.md",
    "ADVANCED-TRAINING-UI.md",
    "FASTFLOWLM-INTEGRATION-TEST-GUIDE.md"
) | ForEach-Object {
    $src = "$repo\docs\$_"
    if (Test-Path $src) {
        Move-Item $src "$internal\docs\" -Force
        Write-Host "MOVED: docs/$_"
    }
}

# Scrapers and dataset builders
@(
    "scrape_boards.py",
    "scrape_boards_bulk.py",
    "build_merged_dataset.py",
    "build_real_dataset.py",
    "enrich_multimodal_dataset.py"
) | ForEach-Object {
    $src = "$repo\scripts\$_"
    if (Test-Path $src) {
        Move-Item $src "$internal\scripts\" -Force
        Write-Host "MOVED: scripts/$_"
    }
}

Write-Host "=== DONE ==="
