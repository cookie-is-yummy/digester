"""PROTOTYPE ONLY - the fixed words of an answer in the person's language (fix pass, finding 15).

A reply is either all in the person's language or all in English, never mixed: the answer's fixed phrases come from
this table for the languages it holds (Spanish so far), and for any other language the whole answer stays English,
including the composer's sentences (it is then not asked to write in that language). Model sentences in a supported
language come from the composer, checked as always.
"""
import re

EN = {
    "recommend": "I recommend",
    "its": "It's",
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
                 "key_points": "The tips are in the video, not written in the post.",
                 "items": "The details are in the post's slides or video, not in its text."},
    # round 7, finding 90: an answer made of the things the posts name
    "items_from": "From \"{title}\"{by}",
    "posted": "posted {when}",
    "kept_head": "{how} {when}",
    "and_more": "and {n} more in the post",
    "items_also": "Also in your saves:",
    # round 8, findings 93 and 94: what was found, with counts; the next posts; a list that is only in the slides
    "items_found": "I found {n} {noun} named in {k} of your saves.",
    "items_found_one": "I found {n} {noun} named in one of your saves.",
    "items_things": "things",
    "items_more": "More in your saves:",
    "items_more_line": "{title}{by}: it names {n} more.",
    "items_more_line_one": "{title}{by}: it names one more.",
    "in_slides": "the names are in its slides, not its text.",
    "same_creator": "same creator as the one you passed on",
    "part_none": "Nothing in your saves clearly fits this part.",
    "parts_stopped": "I stopped there to stay within today's limit, so I didn't search for the rest.",
    "same_creator_lead": "It's by the same creator as the one you passed on.",
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
    # the outside block and the level note, when they ride on an answer (checker, finding 15: never a mixed reply)
    "outside_head": "Not from your saves, but close to them:",
    # fix pass 2, finding 64: said in the request's terms ("saved recipes"), built by code from its goal
    "outside_auto0": "None of your saved {nouns} fits, so here are a few from YouTube:",
    "outside_auto0_any": "Nothing you saved fits, so here are a few from YouTube:",
    "outside_autoN": "You only have {n} saved {noun} that {fit}, so here are a few more from YouTube:",
    "few_finished": "You only have {n} saved {noun} that {fit}.",
    "fit": ("fits", "fit"),
    "go": ("goes", "go"),
    "outside_line": "• {title} by {channel}{length}, on YouTube",
    "outside_cant": None,   # English keeps the exact reason line outside.py gives
    "level": {"new": "I'm guessing you're new to {topic}", "beginner": "I'm guessing you're a beginner at {topic}",
              "intermediate": "I'm guessing you're past the basics with {topic}",
              "advanced": "I'm guessing you're advanced at {topic}"},
    "level_tail": "; tell me if that's wrong.",
    # review fix X4 (experience): a question about picks already shown that their own text does not answer
    "cant_tell_one": "I can't tell that from what {name} says. Here it is, so you can check:",
    "cant_tell_all": "I can't tell that from what those posts say. Open them to check.",
    # review fix X11: "another" once everything that fits was shown
    "more_none": "That's all I have in your saves for \"{goal}\".",
    "more_new": " Say \"new ones\" and I'll look for some on YouTube.",
}

ES = {
    "recommend": "Te recomiendo",
    "its": "Es",
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
                 "key_points": "Los consejos están en el video, no escritos en la publicación.",
                 "items": "Los detalles están en las imágenes o el video de la publicación, no en su texto."},
    "items_from": "De \"{title}\"{by}",
    "posted": "publicado en {when}",
    "kept_head": "{how} en {when}",
    "and_more": "y {n} más en la publicación",
    "items_also": "También en lo que guardaste:",
    "items_found": "Encontré {n} {noun} en {k} de lo que guardaste.",
    "items_found_one": "Encontré {n} {noun} en una de las cosas que guardaste.",
    "items_things": "cosas",
    "items_more": "Más en lo que guardaste:",
    "items_more_line": "{title}{by}: nombra {n} más.",
    "items_more_line_one": "{title}{by}: nombra una más.",
    "in_slides": "los nombres están en sus imágenes, no en su texto.",
    "same_creator": "del mismo creador que el que descartaste",
    "part_none": "Nada de lo que guardaste encaja claramente con esta parte.",
    "parts_stopped": "Paré aquí para no pasar el límite de hoy, así que no busqué el resto.",
    "same_creator_lead": "Es del mismo creador que el que descartaste.",
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
    "none_default": "no hay nada parecido en lo que guardaste",   # review fix X11: not the same words twice
    "none_lib": "nada de tu biblioteca coincide",
    "none_since": "nada de lo que guardaste desde {date} coincide",
    "outside_head": "No está en lo que guardaste, pero se le parece:",
    "outside_auto0": "Lo que guardaste no tiene ninguno de principio a fin, así que aquí tienes algunos de YouTube:",
    "outside_autoN": "Lo que guardaste solo tiene {n} de principio a fin, así que aquí tienes más de YouTube:",
    "few_finished": "Lo que guardaste solo tiene {n} de principio a fin.",
    "go": ("", ""),
    "outside_line": "• {title} de {channel}{length}, en YouTube",
    "outside_cant": "Esta vez no pude buscar cosas nuevas en YouTube.",
    "level": {"new": "Supongo que eres nuevo en {topic}", "beginner": "Supongo que eres principiante en {topic}",
              "intermediate": "Supongo que ya dominas lo básico de {topic}",
              "advanced": "Supongo que tienes un nivel avanzado en {topic}"},
    "level_tail": "; dime si me equivoco.",
    "cant_tell_one": "No lo puedo saber por lo que dice {name}. Aquí está, para que lo mires:",
    "cant_tell_all": "No lo puedo saber por lo que dicen esas publicaciones. Ábrelas para mirarlo.",
    "more_none": "Eso es todo lo que tengo en lo que guardaste para \"{goal}\".",
    # checker, round 2 (finding 62): a request the bot will not do, in a sentence picked by code
    "unsupported": ("Eso no lo puedo hacer. Busco cosas en lo que guardaste y viste, ahora o a la hora que elijas, y "
                    "guardo recordatorios y listas de tareas."),
    "unsupported_event": "No puedo saber cuándo pasa eso. Elige una hora, por ejemplo \"cada día a las 6pm\".",
    "not_caught": "Perdona, no te entendí. ¿Me lo dices de otra forma?",
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
