"""
Dizionari per le misure testuali in stile LIWC.

Le tre misure composite di LIWC-22 richieste dallo sperimentatore — Analytic,
Clout, Authenticity — non dipendono da dizionari di contenuto proprietari: si
reggono quasi interamente sulle *function words* (articoli, preposizioni,
pronomi, ausiliari, congiunzioni, negazioni), che in inglese sono classi
chiuse e di pubblico dominio. È questa la ragione per cui le misure si possono
replicare in modo trasparente senza licenza.

Le categorie di contenuto (emozioni, parolacce, verbi di movimento) sono invece
classi aperte: qui sono liste di semi ad alta frequenza, sufficienti per il
registro di una chat sperimentale ma dichiaratamente non esaustive. Per il
sentiment la misura principale resta VADER, che è validato e open source.

Riferimenti delle formule che usano queste categorie:
- Analytic / CDI: Pennebaker, Chung, Frazee, Lavergne & Beaver (2014), PLOS ONE.
- Clout: Kacewicz, Pennebaker, Davis, Jeon & Graesser (2014), JLSP.
- Authenticity: Newman, Pennebaker, Berry & Richards (2003), PSPB.
"""

# --- Function words: classi chiuse ----------------------------------------

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

# Pronomi personali, suddivisi perché Clout e Authenticity ne usano i
# sottoinsiemi separatamente.
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

# Avverbi: classe aperta. Lista ad alta frequenza, integrata a runtime da una
# euristica sui suffissi -ly con lista di eccezioni (vedi ADVERB_LY_EXCLUDE).
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

# Parole che finiscono in -ly ma non sono avverbi. Nota: "only" non compare
# qui perché in inglese funziona quasi sempre da avverbio ed è già nella lista
# esplicita; "daily", "weekly" e "yearly" sono ambigui (aggettivo o avverbio) e
# si preferisce non contarli.
ADVERB_LY_EXCLUDE = {
    'ally', 'apply', 'assembly', 'belly', 'bully', 'comply', 'daily', 'early',
    'family', 'fly', 'holy', 'italy', 'jelly', 'jolly', 'lily', 'lonely',
    'lovely', 'melancholy', 'monopoly', 'multiply', 'rally', 'rely',
    'reply', 'silly', 'supply', 'ugly', 'weekly', 'yearly',
}

# --- Categorie di contenuto: classi aperte, liste di semi ------------------

# Parole di differenziazione ("exclusive words" in Newman et al. 2003).
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

# Marcatori del linguaggio del gioco: non fanno parte di LIWC, ma sono utili
# come controllo descrittivo del contenuto strategico della chat.
GAME_COMMITMENT = {
    'support', 'supports', 'supporting', 'supported', 'back', 'backing',
    'choose', 'choosing', 'chose', 'pick', 'picking', 'picked', 'vote',
    'coalition', 'ally', 'alliance', 'promise', 'promised', 'deal', 'agree',
    'agreed', 'split', 'share', 'together',
}


def is_adverb(token: str) -> bool:
    """Avverbio per lista esplicita oppure per suffisso -ly non escluso."""
    if token in ADVERBS:
        return True
    return (
        len(token) > 3
        and token.endswith('ly')
        and token not in ADVERB_LY_EXCLUDE
    )


# Categorie esposte all'esterno: nome -> insieme di token.
# `adverbs` non compare qui perché richiede l'euristica sul suffisso.
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
