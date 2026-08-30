# Datasets

Sample datasets and tutorials for NPU-STACK training workflows.

## What goes here (public):
- README.md (this file)
- Sample/tutorial datasets (small, public domain)
- Dataset format documentation
- Dataset preparation guides

## What does NOT go here:
- Training artifacts from NPU-STACK jobs (`.jsonl`, images, models)
- Proprietary datasets
- Scraped data
- Model fine-tuning outputs

Private training data belongs in the separate private training project. A local
working checkout may expose it under `internal/datasets/`, but that path is
gitignored and must never be staged or pushed to public NPU-STACK.
