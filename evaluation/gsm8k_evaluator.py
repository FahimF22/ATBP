import re


def extract_gsm8k_answer(text):
    match = re.search(r"####\s*(-?\d+(?:,\d+)*(?:\.\d+)?)", text)

    if match:
        return match.group(1).replace(",", "")

    return None


def extract_prediction(text):
    if text is None:
        return None
    
    # Priority 1: Look for "**Answer:** <number>" or "Answer: <number>" (case-insensitive)
    answer_pattern = r"\*?\*?Answer\*?\*?:\s*(-?\d+(?:,\d+)*(?:\.\d+)?)"
    match = re.search(answer_pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).replace(",", "")
    
    # Priority 2: Look for "#### <number>" (GSM8K format)
    gsm8k_pattern = r"####\s*(-?\d+(?:,\d+)*(?:\.\d+)?)"
    match = re.search(gsm8k_pattern, text)
    if match:
        return match.group(1).replace(",", "")
    
    # Priority 3: Scan the last 3 sentences/lines for numbers
    # Exclude numbers that are 10 or less AND preceded by 'step', 'iteration', 'attempt', 'part', or numbered list
    lines = text.split('\n')
    last_lines = lines[-3:] if len(lines) >= 3 else lines
    last_text = '\n'.join(last_lines)
    
    # Find all numbers in the last 3 lines
    all_numbers = re.finditer(r"-?\d+(?:,\d+)*(?:\.\d+)?", last_text)
    candidates = []
    for num_match in all_numbers:
        num_str = num_match.group(0)
        num_val = float(num_str.replace(",", ""))
        
        # Check if this number should be excluded
        start_pos = num_match.start()
        prefix = last_text[:start_pos].lower()
        
        # Exclude if number <= 10 and preceded by excluded keywords or numbered list
        if num_val <= 10:
            if any(word in prefix for word in ['step', 'iteration', 'attempt', 'part']):
                continue
            # Check for numbered list pattern (digit followed by period)
            if re.search(r'\d\.\s*$', prefix):
                continue
        
        candidates.append(num_str)
    
    if candidates:
        return candidates[-1].replace(",", "")
    
    # Priority 4: Fall back to the last number in the entire text
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