"""The search models FrameScout can use (E22): the registry the engine's --model and the app read."""
import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchModel:
    """One OpenCLIP model with its weights, as the engine loads it and the app offers it.

    key: the stable name of --model and settings.json; name and pretrained: the OpenCLIP
    model and weights; label: the name shown in the app, the log and the galleries;
    download: the size of the first-use download; cpu_factor: the CPU time per photo part
    relative to the default (measured in PR #13, see docs/BACKLOG-DONE.md E22); image_size: the input
    edge in pixels (tested against the OpenCLIP config; the engine's fallback for the draft
    size); requires: Python packages (import names) the model needs beyond
    requirements.txt of v1.1; multilingual: understands search terms in other languages
    than English (none yet, E21); evaluated: its search quality was measured (E20);
    weights_repo and tokenizer_repo: the Hugging Face Hub repositories open_clip loads the
    weights and a Hugging Face tokenizer from ('' = open_clip's built-in tokenizer; tested
    against the OpenCLIP config), which the engine checks in the cache to load the model
    offline (E16).
    """
    key: str
    name: str
    pretrained: str
    label: str
    download: str
    cpu_factor: str
    image_size: int
    requires: tuple = ()
    multilingual: bool = False
    evaluated: bool = False
    weights_repo: str = ''
    tokenizer_repo: str = ''


# The default comes first. User decisions: the default stays OpenAI CLIP ViT-B/32 (PR #13);
# offered besides it are ViT-B/16 and ViT-L/14 (DataComp-XL) and SigLIP B/16, not evaluated
# yet: a follow-up item evaluates them and trims the list (E22). The OpenAI weights were
# trained with QuickGELU, so the "-quickgelu" config (E1).
MODELS = {model.key: model for model in (
    SearchModel('vit-b-32-openai', 'ViT-B-32-quickgelu', 'openai', 'ViT-B/32 · OpenAI CLIP', '605 MB', '1×',
                224, evaluated=True, weights_repo='timm/vit_base_patch32_clip_224.openai'),
    SearchModel('vit-b-16-datacomp', 'ViT-B-16', 'datacomp_xl_s13b_b90k', 'ViT-B/16 · DataComp-XL', '599 MB', '~4×',
                224, weights_repo='laion/CLIP-ViT-B-16-DataComp.XL-s13B-b90K'),
    SearchModel('vit-l-14-datacomp', 'ViT-L-14', 'datacomp_xl_s13b_b90k', 'ViT-L/14 · DataComp-XL', '1.71 GB', '~18×',
                224, weights_repo='laion/CLIP-ViT-L-14-DataComp.XL-s13B-b90K'),
    SearchModel('vit-b-16-siglip', 'ViT-B-16-SigLIP', 'webli', 'ViT-B/16 · SigLIP WebLI', '813 MB', '~4×',
                224, requires=('transformers',), weights_repo='timm/ViT-B-16-SigLIP',
                tokenizer_repo='timm/ViT-B-16-SigLIP'),
)}
DEFAULT_MODEL = 'vit-b-32-openai'
# the choices of --model and of the app's selectbox, the default first
MODEL_KEYS = tuple(MODELS)


def _model(key):
    try:
        return MODELS[key]
    except (KeyError, TypeError):
        raise ValueError(f'Unknown search model {key!r}; known: {", ".join(MODEL_KEYS)}') from None


def model_label(key):
    """Return the label of the app's model choice, e.g. "ViT-B/16 · DataComp-XL (~4× slower on a CPU; ...)"."""
    model = _model(key)
    if key == DEFAULT_MODEL:
        return f'{model.label} (default, fastest; {model.download} download)'
    note = '' if model.evaluated else '; not evaluated'
    return f'{model.label} ({model.cpu_factor} slower on a CPU; {model.download} download{note})'


def results_model(settings):
    """Return the search model key of a search from its results.json settings (a dict).

    A search before E22 used the default model and does not name it. Anything other than a
    string (a damaged file) is returned as None.
    """
    key = settings.get('model', DEFAULT_MODEL) if isinstance(settings, dict) else DEFAULT_MODEL
    return key if isinstance(key, str) else None


def missing_packages(key, find_spec=importlib.util.find_spec):
    """Return the packages the search model key needs that are not installed (find_spec(name) is None)."""
    return [name for name in _model(key).requires if find_spec(name) is None]


def model_problem(key, find_spec=importlib.util.find_spec):
    """Return why the search model key cannot be used in this Python environment, or None."""
    missing = missing_packages(key, find_spec)
    if not missing:
        return None
    names = ', '.join(missing)
    return (f'The search model {_model(key).label} needs the Python package{"s" if len(missing) > 1 else ""} '
            f'{names}, which {"are" if len(missing) > 1 else "is"} not installed. Run Install-FrameScout.bat again '
            '(or pip install -r requirements.txt -c constraints.txt), or choose another search model.')
