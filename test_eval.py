from interview_coach import evaluate_answer

q = "What is a list comprehension in Python?"

good = "It is a short syntax to build a new list from an iterable, like [x*2 for x in nums if x > 0]."
bad = "It is a type of loop used in Java to compare two lists."

for label, ans in [("GOOD", good), ("BAD", bad), ("EMPTY", "")]:
    ev = evaluate_answer("Python", q, ans)
    print(label, ev.concept, ev.accuracy, ev.clarity, "|", ev.feedback)