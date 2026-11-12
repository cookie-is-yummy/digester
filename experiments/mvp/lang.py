"""PROTOTYPE ONLY - the fixed words of an answer in the person's language (fix pass, finding 15).

A reply is either all in the person's language or all in English, never mixed: the answer's fixed phrases come from
this table for the languages it holds (Spanish so far), and for any other language the whole answer stays English,
including the composer's sentences (it is then not asked to write in that language). Model sentences in a supported
language come from the composer, checked as always.
"""
import re

EN = {
    "recommend": "I recommend",
    "closest": "The closest I have is",
    "no_clear": "Nothing I found is a clear fit for \"{goal}\".",
    "lead_unknown": "I couldn't confirm any of these {phrase}, but the closest I have is",
    "lead_no": "None of what I found {phrase}, so the closest I have is",
    "ph_recipe": "is a whole recipe you can cook",
    "ph_routine": "is a full routine from start to finish",
    "ph_project": "walks you through a whole project",
    "ph_under": "is under {n} minutes long",
    "ph_fits": "clearly fits \"{cr}\"",
    "ph_fits_no": "fits \"{cr}\"",
    "or_try": "Or try these:",
    "or_close": "Or these, which are close too:",
    "wider": "Or here's a wider selection:",
    "cant_check": "I couldn't check \"{cr}\" for any of these: the posts don't say.",
    "top_n": "You asked for {asked}, so here are the top {n}.",
    "intro_a": "I found {goal} in your saves.",
    "intro_for": "Here's what I found in your saves for {goal}.",
    "intro_plain": "Here's what I found in your saves.",
    "by": " by {creator}",
    "kept": "which you {how} in {when}",
    "kept_plain": "which you {how}",
    "because": "because",
    "how": {"save": "saved", "collection": "put in a collection", "share_self": "sent to yourself",
            "playlist": "added to a playlist", "like": "liked", "watch": "watched", "view": "viewed"},
    "label": {"ingredients": "Ingredients", "steps": "Steps", "key_points": "Key points", "details": "Details"},
    "in_video": {"ingredients": "The recipe is in the video, not written in the post.",
                 "steps": "The steps are in the video, not written in the post.",
                 "key_points": "The tips are in the video, not written in the post."},
    "not_written": {"ingredients": "The ingredients aren't written out in the post; they're in the video.",
                    "steps": "The steps aren't written out in the post; they're in the video.",
                    "key_points": "The key points aren't written out in the post; they're in the video."},
    "alt_ing_steps": "the ingredients and steps are written out",
    "alt_ing": "the ingredients are written out",
    "amounts": ", with amounts",
    "alt_steps": "the steps are written out",
    "alt_keys": "the tips are written out",
    "alt_video": "the recipe is in the video",
    "none": "I didn't find a good match: {reason}.",
    "none_default": "nothing in your library fits well",
    "none_lib": "nothing in your library matched",
    "none_since": "nothing you kept since {date} matched",
    "months": None,
}

ES = {
    "recommend": "Te recomiendo",
    "closest": "Lo más parecido que tengo es",
    "no_clear": "No encontré nada que encaje del todo con \"{goal}\".",
    "lead_unknown": "No pude confirmar que alguno {phrase}, pero lo más parecido que tengo es",
    "lead_no": "Nada de lo que encontré {phrase}, así que lo más parecido que tengo es",
    "ph_recipe": "sea una receta completa para cocinar",
    "ph_routine": "sea una rutina completa de principio a fin",
    "ph_project": "te guíe por un proyecto completo",
    "ph_under": "dure menos de {n} minutos",
    "ph_fits": "cumpla claramente \"{cr}\"",
    "ph_fits_no": "cumple \"{cr}\"",
    "or_try": "O prueba estos:",
    "or_close": "O estos, que también se acercan:",
    "wider": "O aquí tienes más opciones:",
    "cant_check": "No pude comprobar \"{cr}\" en ninguno: las publicaciones no lo dicen.",
    "top_n": "Pediste {asked}, así que aquí tienes los {n} mejores.",
    "intro_a": "Encontré esto en lo que guardaste.",
    "intro_for": "Esto es lo que encontré en lo que guardaste.",
    "intro_plain": "Esto es lo que encontré en lo que guardaste.",
    "by": " de {creator}",
    "kept": "que {how} en {when}",
    "kept_plain": "que {how}",
    "because": "porque",
    "how": {"save": "guardaste", "collection": "pusiste en una colección", "share_self": "te enviaste",
            "playlist": "añadiste a una lista", "like": "te gustó", "watch": "viste", "view": "viste"},
    "label": {"ingredients": "Ingredientes", "steps": "Pasos", "key_points": "Puntos clave", "details": "Detalles"},
    "in_video": {"ingredients": "La receta está en el video, no escrita en la publicación.",
                 "steps": "Los pasos están en el video, no escritos en la publicación.",
                 "key_points": "Los consejos están en el video, no escritos en la publicación."},
    "not_written": {"ingredients": "Los ingredientes no están escritos en la publicación; están en el video.",
                    "steps": "Los pasos no están escritos en la publicación; están en el video.",
                    "key_points": "Los puntos clave no están escritos en la publicación; están en el video."},
    "alt_ing_steps": "los ingredientes y los pasos están escritos",
    "alt_ing": "los ingredientes están escritos",
    "amounts": ", con cantidades",
    "alt_steps": "los pasos están escritos",
    "alt_keys": "los consejos están escritos",
    "alt_video": "la receta está en el video",
    "none": "No encontré nada que encaje bien: {reason}.",
    "none_default": "nada de tu biblioteca encaja bien",
    "none_lib": "nada de tu biblioteca coincide",
    "none_since": "nada de lo que guardaste desde {date} coincide",
    "months": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
               "noviembre", "diciembre"],
}

TABLES = {"es": ES}


def code(lang):
    """'es' for 'es', 'es-MX', 'spanish'; None for English or nothing."""
    v = (lang or "").strip().lower()
    if not v or v.startswith("en") or v == "english":
        return None
    return {"spanish": "es", "español": "es", "espanol": "es", "french": "fr", "chinese": "zh"}.get(v, v[:2])


def supported(lang):
    return code(lang) in TABLES


def table(lang):
    """The phrase table for the answer: the person's language when it has one, else English."""
    return TABLES.get(code(lang), EN)


def month(d, lang, with_year):
    t = table(lang)
    if t["months"]:
        name = t["months"][d.month - 1]
        return f"{name} de {d.year}" if with_year else name
    return d.strftime("%B %Y") if with_year else d.strftime("%B")


_LEN_ES = [(r"\bunder a minute\b", "menos de un minuto"), (r"\bhours\b", "horas"), (r"\bhour\b", "hora"),
           (r"\bminutes\b", "minutos"), (r"\bminute\b", "minuto"), (r"\bseconds\b", "segundos"),
           (r"\bsecond\b", "segundo")]


def length(text, lang):
    if code(lang) != "es" or not text:
        return text
    for a, b in _LEN_ES:
        text = re.sub(a, b, text)
    return text
