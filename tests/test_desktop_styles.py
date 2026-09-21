from jiezhi.desktop_styles import style_instruction,preset,clauses,summary,PLAIN,MAX_WEIGHT


def test_no_weight_falls_back_to_a_plain_rewrite():
    assert style_instruction({})==PLAIN and style_instruction({'comedy':0})==PLAIN


def test_a_dimension_at_zero_is_left_out_of_the_prompt():
    text=style_instruction({'comedy':0,'professionalism':8})
    assert 'professional' in text and 'humour' not in text and 'comedic' not in text


def test_clauses_are_ordered_strongest_first():
    assert clauses({'comedy':2,'professionalism':9,'warmth':5})==[
        'a formal professional register','a warm and friendly tone','a light touch of humour']


def test_a_preset_is_one_dimension_at_full_weight():
    weights=preset('casualness')
    assert weights['casualness']==MAX_WEIGHT and sum(weights.values())==MAX_WEIGHT


def test_weights_outside_the_range_are_clamped_or_ignored():
    assert style_instruction({'comedy':99})==style_instruction({'comedy':MAX_WEIGHT})
    assert style_instruction({'comedy':-4})==PLAIN and style_instruction({'comedy':'loud'})==PLAIN


def test_summary_names_the_two_strongest():
    assert summary({'professionalism':10,'casualness':5,'warmth':1})=='Professional, Casual'
