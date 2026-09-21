"""Weighted writing styles for the rewrite action, expressed as plain instructions."""

MAX_WEIGHT=10

# Each dimension carries the clause used when it is lightly, moderately or strongly weighted.
STYLE_DIMENSIONS=(
 ('comedy','Comedy',('a light touch of humour','a playful and funny tone','a strongly comedic tone that plays the subject for laughs')),
 ('professionalism','Professional',('a slightly more professional tone','a professional and businesslike tone','a formal professional register')),
 ('casualness','Casual',('a slightly relaxed voice','a casual conversational voice','a very casual voice as if speaking to a friend')),
 ('warmth','Warm',('a slightly warmer tone','a warm and friendly tone','a notably warm and encouraging tone')),
 ('directness','Direct',('a little more directness','a direct tone that comes to the point','a blunt and maximally direct tone that never hedges')),
)

PLAIN='Rewrite the selected text for clarity and fluency. Keep its meaning. Return only the revised text.'


def preset(key):
    """Everything to zero except one dimension, which goes to the top of its range."""
    return {name:(MAX_WEIGHT if name==key else 0) for name,_,_ in STYLE_DIMENSIONS}


def clauses(weights):
    """Strongest first, in plain language. A dimension at zero is left out entirely:
    naming it would put the word in the prompt and pull the model toward it."""
    chosen=[]
    for key,_,text in STYLE_DIMENSIONS:
        try:value=int(weights.get(key,0))
        except (TypeError,ValueError):continue
        if value<=0:continue
        value=min(value,MAX_WEIGHT)
        chosen.append((value,text[0 if value<4 else 1 if value<8 else 2]))
    chosen.sort(key=lambda pair:-pair[0])
    return [text for _,text in chosen]


def style_instruction(weights):
    parts=clauses(weights or {})
    if not parts:return PLAIN
    styled=parts[0] if len(parts)==1 else ', '.join(parts[:-1])+' and '+parts[-1]
    return ('Rewrite the selected text with '+styled+'. Keep its meaning and every fact it states, '
            'do not add information it does not contain, and return only the rewritten text.')


def summary(weights):
    """Short label for the result window, e.g. 'Professional, Warm'."""
    named=[(int(weights.get(key,0)),label) for key,label,_ in STYLE_DIMENSIONS if int(weights.get(key,0))>0]
    named.sort(key=lambda pair:-pair[0])
    return ', '.join(label for _,label in named[:2])
