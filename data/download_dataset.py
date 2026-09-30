from datasets import load_dataset


def load_gsm8k(split="test"):
    dataset = load_dataset(
        "openai/gsm8k",
        "main",
        split=split
    )

    return dataset


if __name__ == "__main__":
    dataset = load_gsm8k()

    print("Number of examples:", len(dataset))
    print(dataset[0])