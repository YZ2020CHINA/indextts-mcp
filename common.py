"""Shared validation and persistence; no model imports in the MCP process."""
from pathlib import Path
import ast
import json
import math
import os
import uuid
import wave

VERSION = '1.2.0'
APP = 'pink-bird-indextts'
LANGUAGES = ['ZH', 'EN', 'JA', 'AR', 'ES']
EMOTIONS = ['happy', 'angry', 'sad', 'afraid', 'disgusted', 'melancholic', 'surprised', 'calm']


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def number(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, int if integer else (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be {"integer" if integer else "number"} in [{low}, {high}]')
    return value


def audio_path(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError('Reference audio must be an absolute local file path')
    path = Path(value).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in ('.wav', '.mp3', '.flac', '.m4a', '.ogg'):
        raise ValueError('Reference must be a WAV/MP3/FLAC/M4A/OGG file')
    if not 44 < path.stat().st_size <= 100 * 1024 * 1024:
        raise ValueError('Reference audio must be nonempty and at most 100 MiB')
    return str(path)


def validate(args, config):
    allowed = {'text','reference_audio','language','duration_factor','emotion_audio','emotion_vector','emotion_text','use_emotion_text','emotion_weight','random_emotion','max_tokens_per_segment','temperature','top_p','top_k','num_beams','seed','do_sample','length_penalty','repetition_penalty','max_mel_tokens','interval_silence_ms','text_normalization'}
    extra = set(args) - allowed
    if extra:
        raise ValueError(f'Unknown parameters: {sorted(extra)}')
    text = args.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > config.get('max_text_chars', 5000):
        raise ValueError('text must be nonempty and within max_text_chars')
    language = args.get('language', 'ZH')
    if language not in LANGUAGES:
        raise ValueError(f'language must be one of {LANGUAGES}')
    result = dict(text=text, reference_audio=audio_path(args.get('reference_audio')), language=language)
    result['duration_factor'] = number(args.get('duration_factor', 1.0), 'duration_factor', .5, 2)
    result['emotion_weight'] = number(args.get('emotion_weight', .65), 'emotion_weight', 0, 1)
    for key,default in [('use_emotion_text',False),('random_emotion',False),('do_sample',True),('text_normalization',True)]:
        result[key]=args.get(key,default)
        if not isinstance(result[key],bool):
            raise ValueError(f'{key} must be boolean')
    # An explicit description implies text-emotion inference; the bool also enables
    # the official fallback of deriving emotion from the script itself.
    emo_text=args.get('emotion_text')
    if emo_text is not None:
        if not isinstance(emo_text,str) or not emo_text.strip() or len(emo_text)>500:
            raise ValueError('emotion_text must be nonempty with at most 500 characters')
        result['emotion_text']=emo_text
        result['use_emotion_text']=True
    modes = [args.get('emotion_audio') is not None,args.get('emotion_vector') is not None,result['use_emotion_text']]
    if sum(modes) > 1:
        raise ValueError('Choose only one of emotion_audio, emotion_vector, emotion_text')
    if modes[0]:
        result['emotion_audio'] = audio_path(args['emotion_audio'])
    if modes[1]:
        vec = args['emotion_vector']
        if not isinstance(vec, list) or len(vec) != 8:
            raise ValueError(f'emotion_vector requires 8 numbers: {EMOTIONS}')
        result['emotion_vector'] = [number(v, 'emotion_vector', 0, 1) for v in vec]
    if modes[2]:
        if not config.get('use_qwen_emo'):
            raise ValueError('Emotion text requires use_qwen_emo=true in config and a backend restart; needs extra VRAM')
    for key, default, low, high, integer in [('max_tokens_per_segment',120,20,600,True),('temperature',.8,.1,2,False),('top_p',.8,.01,1,False),('top_k',30,0,100,True),('num_beams',3,1,10,True),('length_penalty',0.,-2,2,False),('repetition_penalty',10.,.1,20,False),('max_mel_tokens',1500,50,4096,True),('interval_silence_ms',200,0,2000,True)]:
        result[key] = number(args.get(key, default), key, low, high, integer)
    if 'seed' in args:
        result['seed'] = number(args['seed'], 'seed', 0, 4294967295, True)
    return result


def inference_kwargs(params, output, model):
    """Map the public names to the actual upstream API in one tested place."""
    vec=params.get('emotion_vector')
    if vec is not None:
        vec=model.normalize_emo_vec(vec,apply_bias=True)
    return dict(spk_audio_prompt=params['reference_audio'],text=params['text'],lang=params['language'],output_path=str(output),
                emo_audio_prompt=params.get('emotion_audio'),emo_alpha=params['emotion_weight'],emo_vector=vec,
                use_emo_text=params['use_emotion_text'],emo_text=params.get('emotion_text'),use_random=params['random_emotion'],
                duration_factor=params['duration_factor'],max_text_tokens_per_segment=params['max_tokens_per_segment'],
                do_sample=params['do_sample'],temperature=params['temperature'],top_p=params['top_p'],top_k=params['top_k'] or None,
                num_beams=params['num_beams'],length_penalty=params['length_penalty'],repetition_penalty=params['repetition_penalty'],
                max_mel_tokens=params['max_mel_tokens'],interval_silence=params['interval_silence_ms'],
                text_normalization=params['text_normalization'],verbose=False)


def sampling_switch_supported(source):
    """Some installed bundles hardcode do_sample=True despite accepting the arg."""
    tree=ast.parse(Path(source).read_text(encoding='utf-8-sig'))
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
           and n.func.attr=='inference_speech']
    return bool(calls) and all(any(k.arg=='do_sample' and isinstance(k.value,ast.Name)
                                  and k.value.id=='do_sample' for k in call.keywords) for call in calls)


def wav_info(path):
    with wave.open(str(path), 'rb') as audio:
        if audio.getnframes() == 0:
            raise ValueError('Model returned an empty WAV')
        return {'path':str(Path(path).resolve()), 'sample_rate':audio.getframerate(),
                'channels':audio.getnchannels(), 'duration_seconds':round(audio.getnframes()/audio.getframerate(),3),
                'bytes':Path(path).stat().st_size}
