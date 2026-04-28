"""Unsloth LoRA fine-tune script for qwen3:30b-a3b on career Q&A dataset.

Requirements:
  pip install unsloth transformers datasets trl peft bitsandbytes

Hardware: M3 Max 36GB — uses 4-bit quantisation + LoRA (runs in ~24GB)

Usage:
  python eval/finetune/finetune_qwen3_30b.py
  python eval/finetune/finetune_qwen3_30b.py --dataset eval/sft_dataset.jsonl --output models/qwen3-30b-career-lora
  python eval/finetune/finetune_qwen3_30b.py --export-gguf   # after training

After training, export and register:
  python eval/finetune/finetune_qwen3_30b.py --export-gguf
  ollama create qwen3-30b-career -f models/Modelfile.qwen3-30b-career
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SFT_DATASET = Path("eval/sft_dataset.jsonl")
OUTPUT_DIR = Path("models/qwen3-30b-career-lora")
BASE_MODEL = "Qwen/Qwen3-30B-A3B"   # HuggingFace model id (or local path)
GGUF_OUTPUT = Path("models/qwen3-30b-career.gguf")
MODELFILE_OUTPUT = Path("models/Modelfile.qwen3-30b-career")


def load_dataset_records(path: Path) -> list[dict]:
    records = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def format_chat(record: dict, tokenizer) -> str:
    """Convert chat-format record to tokenizer chat template."""
    return tokenizer.apply_chat_template(
        record["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )


def train(dataset_path: Path, output_dir: Path) -> None:
    try:
        from unsloth import FastLanguageModel
        from trl import SFTTrainer, SFTConfig
        from datasets import Dataset
    except ImportError as exc:
        raise SystemExit(
            "Install dependencies: pip install unsloth transformers datasets trl peft bitsandbytes"
        ) from exc

    print(f"Loading base model: {BASE_MODEL}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=4096,
        dtype=None,           # auto-detect (bfloat16 on M3 Max)
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=16,                 # LoRA rank
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    records = load_dataset_records(dataset_path)
    print(f"Loaded {len(records)} training examples from {dataset_path}")

    texts = [format_chat(r, tokenizer) for r in records]
    dataset = Dataset.from_dict({"text": texts})

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            output_dir=str(output_dir),
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            num_train_epochs=3,
            learning_rate=2e-4,
            fp16=False,
            bf16=True,
            logging_steps=10,
            save_strategy="epoch",
            warmup_ratio=0.03,
            lr_scheduler_type="cosine",
            dataset_text_field="text",
            max_seq_length=4096,
            report_to="none",
        ),
    )

    print("Starting fine-tune...")
    trainer.train()
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print(f"Saved LoRA adapter → {output_dir}")


def export_gguf(lora_dir: Path) -> None:
    """Merge LoRA adapter and export to GGUF via llama.cpp convert script."""
    try:
        from unsloth import FastLanguageModel
    except ImportError as exc:
        raise SystemExit("Install unsloth: pip install unsloth") from exc

    merged_dir = lora_dir.parent / (lora_dir.name + "-merged")
    print(f"Merging LoRA adapter into full model → {merged_dir}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(lora_dir),
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=False,
    )
    model.save_pretrained_merged(str(merged_dir), tokenizer, save_method="merged_16bit")

    print("Converting to GGUF (Q4_K_M)...")
    convert_script = Path("llama.cpp/convert-hf-to-gguf.py")
    if not convert_script.exists():
        raise SystemExit(
            "llama.cpp not found. Clone it: git clone https://github.com/ggerganov/llama.cpp"
        )

    import subprocess
    subprocess.run(
        ["python", str(convert_script), str(merged_dir),
         "--outtype", "q4_k_m", "--outfile", str(GGUF_OUTPUT)],
        check=True,
    )

    modelfile_content = f"""FROM {GGUF_OUTPUT.resolve()}
PARAMETER num_ctx 16384
PARAMETER num_gpu 99
PARAMETER temperature 0.7
PARAMETER top_p 0.9
"""
    MODELFILE_OUTPUT.write_text(modelfile_content)
    print(f"GGUF → {GGUF_OUTPUT}")
    print(f"Modelfile → {MODELFILE_OUTPUT}")
    print()
    print("Register with ollama:")
    print(f"  ollama create qwen3-30b-career -f {MODELFILE_OUTPUT}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune qwen3-30b on career Q&A")
    parser.add_argument("--dataset", type=Path, default=SFT_DATASET)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--export-gguf", action="store_true",
                        help="Merge LoRA and export GGUF (skip training)")
    args = parser.parse_args()

    if args.export_gguf:
        export_gguf(args.output)
    else:
        if not args.dataset.exists():
            raise SystemExit(
                f"Dataset not found: {args.dataset}\n"
                "Run first: python scripts/build_sft_dataset.py --url http://localhost:8000 --token <JWT>"
            )
        train(args.dataset, args.output)


if __name__ == "__main__":
    main()
