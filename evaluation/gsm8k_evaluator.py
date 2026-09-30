import re


def extract_gsm8k_answer(text):
    match = re.search(r"####\s*(-?\d+(?:,\d+)*(?:\.\d+)?)", text)

    if match:
        return match.group(1).replace(",", "")

    return None


def extract_prediction(text):
    numbers = re.findall(
        r"-?\d+(?:,\d+)*(?:\.\d+)?",
        text
    )

    if not numbers:
        return None

    return numbers[-1].replace(",", "")


def evaluate_answer(prediction_text, ground_truth_text):

    prediction = extract_prediction(prediction_text)
    ground_truth = extract_gsm8k_answer(ground_truth_text)

    if prediction is None or ground_truth is None:
        return False, prediction, ground_truth

    return (
        prediction == ground_truth,
        prediction,
        ground_truth
    )