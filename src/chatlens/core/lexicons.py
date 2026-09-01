"""
Dictionaries for the LIWC-style text measures.

The three LIWC-22 composites the experimenter asked for — Analytic, Clout,
Authenticity — do not depend on proprietary content dictionaries: they rest
almost entirely on *function words* (articles, prepositions, pronouns,
auxiliaries, conjunctions, negations), which in English are closed classes and
in the public domain. That is why the measures can be replicated transparently
without a licence.

Content categories (emotion, swearing, motion verbs) are open classes: what
follows are high-frequency seed lists, adequate for the register of an
experimental chat but avowedly not exhaustive. For sentiment the primary
measure remains VADER, which is validated and open source.

References for the formulas that use these categories:
- Analytic / CDI: Pennebaker, Chung, Frazee, Lavergne & Beaver (2014), PLOS ONE.
- Clout: Kacewicz, Pennebaker, Davis, Jeon & Graesser (2014), JLSP.
- Authenticity: Newman, Pennebaker, Berry & Richards (2003), PSPB.
"""

# --- Function words: closed classes ----------------------------------------

ARTICLES = {'a', 'an', 'the'}

PREPOSITIONS = {
    'about', 'above', 'across', 'after', 'against', 'along', 'among', 'around',
    'as', 'at', 'before', 'behind', 'below', 'beneath', 'beside', 'besides',
    'between', 'beyond', 'by', 'concerning', 'despite', 'down', 'during',
    'except', 'for', 'from', 'in', 'inside', 'into', 'like', 'near', 'of',
    'off', 'on', 'onto', 'out', 'outside', 'over', 'past', 'per', 'regarding',
    'since', 'through', 'throughout', 'till', 'to', 'toward', 'towards',
    'under', 'underneath', 'until', 'unto', 'up', 'upon', 'with', 'within',
    'without',
}

# Personal pronouns, split because Clout and Authenticity use the subsets
# separately.
PRONOUNS_I = {'i', 'me', 'my', 'mine', 'myself', "i'm", "i've", "i'll", "i'd"}
PRONOUNS_WE = {'we', 'us', 'our', 'ours', 'ourselves', "we're", "we've", "we'll", "we'd"}
PRONOUNS_YOU = {
    'you', 'your', 'yours', 'yourself', 'yourselves', 'u', 'ur',
    "you're", "you've", "you'll", "you'd",
}
PRONOUNS_SHEHE = {
    'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself',
    "he's", "she's", "he'll", "she'll", "he'd", "she'd",
}
PRONOUNS_THEY = {
    'they', 'them', 'their', 'theirs', 'themselves',
    "they're", "they've", "they'll", "they'd",
}

PERSONAL_PRONOUNS = (
    PRONOUNS_I | PRONOUNS_WE | PRONOUNS_YOU | PRONOUNS_SHEHE | PRONOUNS_THEY
)

IMPERSONAL_PRONOUNS = {
    'it', 'its', 'itself', "it's", 'this', 'that', 'these', 'those',
    'something', 'anything', 'nothing', 'everything', 'someone', 'anyone',
    'everyone', 'nobody', 'somebody', 'anybody', 'everybody', 'one', 'ones',
    'all', 'some', 'any', 'both', 'each', 'either', 'neither', 'few', 'many',
    'most', 'much', 'other', 'others', 'several', 'such', 'what', 'whatever',
    'which', 'whichever', 'who', 'whoever', 'whom', 'whose',
}

AUXILIARY_VERBS = {
    'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'having',
    'do', 'does', 'did', 'doing',
    'will', 'would', 'shall', 'should', 'can', 'could', 'may', 'might', 'must',
    "'m", "'re", "'s", "'ve", "'ll", "'d",
    "isn't", "aren't", "wasn't", "weren't", "haven't", "hasn't", "hadn't",
    "don't", "doesn't", "didn't", "won't", "wouldn't", "shouldn't", "can't",
    "cannot", "couldn't", "mustn't", "shan't", "mightn't",
}

CONJUNCTIONS = {
    'and', 'but', 'or', 'nor', 'yet', 'so', 'because', 'cause', 'cuz',
    'although', 'though', 'since', 'unless', 'while', 'whilst', 'whereas',
    'if', 'when', 'whenever', 'whether', 'than', 'therefore', 'thus',
    'however', 'moreover', 'nevertheless', 'plus', 'also',
}

NEGATIONS = {
    'no', 'not', 'never', 'none', 'nothing', 'nobody', 'nowhere', 'neither',
    'nor', 'cannot', 'without', "n't", "don't", "doesn't", "didn't", "won't",
    "wouldn't", "shouldn't", "can't", "couldn't", "isn't", "aren't", "wasn't",
    "weren't", "haven't", "hasn't", "hadn't", "ain't", 'nope', 'nah',
}

# Adverbs: an open class. High-frequency list, extended at runtime by a suffix
# heuristic on -ly with a list of exceptions (see ADVERB_LY_EXCLUDE).
ADVERBS = {
    'very', 'really', 'just', 'so', 'too', 'quite', 'rather', 'almost',
    'always', 'never', 'often', 'sometimes', 'usually', 'rarely', 'seldom',
    'again', 'already', 'still', 'yet', 'soon', 'now', 'then', 'here', 'there',
    'maybe', 'perhaps', 'probably', 'possibly', 'definitely', 'certainly',
    'actually', 'basically', 'literally', 'totally', 'absolutely', 'exactly',
    'pretty', 'somewhat', 'enough', 'even', 'only', 'also', 'well', 'better',
    'best', 'worse', 'worst', 'more', 'less', 'most', 'least', 'much',
    'together', 'instead', 'anyway', 'anyhow', 'otherwise', 'indeed', 'sure',
    'ok', 'okay', 'yes', 'yeah', 'yep', 'hopefully', 'obviously',
}

# Words ending in -ly that are not adverbs. Note: "only" is absent because in
# English it almost always works as an adverb and is already in the explicit
# list; "daily", "weekly" and "yearly" are ambiguous (adjective or adverb) and
# we prefer not to count them.
ADVERB_LY_EXCLUDE = {
    'ally', 'apply', 'assembly', 'belly', 'bully', 'comply', 'daily', 'early',
    'family', 'fly', 'holy', 'italy', 'jelly', 'jolly', 'lily', 'lonely',
    'lovely', 'melancholy', 'monopoly', 'multiply', 'rally', 'rely',
    'reply', 'silly', 'supply', 'ugly', 'weekly', 'yearly',
}

# --- Content categories: open classes, seed lists ---------------------------

# Differentiation words ("exclusive words" in Newman et al. 2003).
EXCLUSIVE = {
    'but', 'except', 'without', 'exclude', 'excluding', 'unless', 'however',
    'although', 'though', 'rather', 'instead', 'whereas', 'than', 'besides',
    'otherwise', 'nor', 'versus', 'vs',
}

MOTION_VERBS = {
    'go', 'goes', 'going', 'gone', 'went', 'come', 'comes', 'coming', 'came',
    'move', 'moves', 'moving', 'moved', 'walk', 'walks', 'walking', 'walked',
    'run', 'runs', 'running', 'ran', 'leave', 'leaves', 'leaving', 'left',
    'arrive', 'arrives', 'arriving', 'arrived', 'travel', 'travels',
    'drive', 'drives', 'driving', 'drove', 'carry', 'carries', 'carrying',
    'bring', 'brings', 'bringing', 'brought', 'take', 'takes', 'taking',
    'took', 'follow', 'follows', 'following', 'followed', 'enter', 'exit',
    'return', 'returns', 'returning', 'returned', 'send', 'sends', 'sent',
}

SWEAR = {
    'damn', 'damned', 'hell', 'shit', 'shitty', 'crap', 'crappy', 'fuck',
    'fucking', 'fucked', 'bitch', 'ass', 'asshole', 'bastard', 'idiot',
    'stupid', 'dumb', 'moron', 'wtf', 'stfu', 'bs',
}

SOCIAL = (
    PRONOUNS_WE | PRONOUNS_YOU | PRONOUNS_SHEHE | PRONOUNS_THEY | {
        'friend', 'friends', 'partner', 'partners', 'team', 'group', 'people',
        'everyone', 'together', 'talk', 'talking', 'tell', 'told', 'say',
        'said', 'ask', 'asked', 'agree', 'agreed', 'deal', 'trust', 'help',
    }
)

POSITIVE_EMOTION = {
    'good', 'great', 'nice', 'happy', 'glad', 'love', 'like', 'liked', 'best',
    'better', 'perfect', 'awesome', 'excellent', 'fair', 'fine', 'cool',
    'thanks', 'thank', 'please', 'yes', 'sure', 'agree', 'agreed', 'win',
    'winning', 'benefit', 'trust', 'friendly', 'safe', 'sweet', 'lol', 'haha',
    'welcome', 'hope', 'hopefully', 'right',
}

NEGATIVE_EMOTION = {
    'bad', 'worse', 'worst', 'hate', 'angry', 'mad', 'sad', 'sorry', 'afraid',
    'scared', 'worry', 'worried', 'annoying', 'annoyed', 'unfair', 'lose',
    'losing', 'lost', 'lie', 'lying', 'liar', 'cheat', 'cheating', 'betray',
    'betrayed', 'risk', 'risky', 'problem', 'wrong', 'fail', 'failed',
    'nothing', 'never', 'no', 'sucks', 'ugh',
} | SWEAR

# Markers of the game's own language: not part of LIWC, but a useful
# descriptive check on the strategic content of the chat.
GAME_COMMITMENT = {
    'support', 'supports', 'supporting', 'supported', 'back', 'backing',
    'choose', 'choosing', 'chose', 'pick', 'picking', 'picked', 'vote',
    'coalition', 'ally', 'alliance', 'promise', 'promised', 'deal', 'agree',
    'agreed', 'split', 'share', 'together',
}


def is_adverb(token: str) -> bool:
    """An adverb by explicit list, or by a non-excluded -ly suffix."""
    if token in ADVERBS:
        return True
    return (
        len(token) > 3
        and token.endswith('ly')
        and token not in ADVERB_LY_EXCLUDE
    )


# Categories exposed to the outside: name -> set of tokens.
# `adverbs` is absent here because it needs the suffix heuristic.
CATEGORIES = {
    'article': ARTICLES,
    'prep': PREPOSITIONS,
    'ppron': PERSONAL_PRONOUNS,
    'ipron': IMPERSONAL_PRONOUNS,
    'auxverb': AUXILIARY_VERBS,
    'conj': CONJUNCTIONS,
    'negate': NEGATIONS,
    'i': PRONOUNS_I,
    'we': PRONOUNS_WE,
    'you': PRONOUNS_YOU,
    'shehe': PRONOUNS_SHEHE,
    'they': PRONOUNS_THEY,
    'social': SOCIAL,
    'exclusive': EXCLUSIVE,
    'motion': MOTION_VERBS,
    'swear': SWEAR,
    'posemo': POSITIVE_EMOTION,
    'negemo': NEGATIVE_EMOTION,
    'commitment': GAME_COMMITMENT,
}
