"""Generación de la sugerencia de respuesta a partir de los artículos recuperados.

- Modo "extractivo" (por defecto, sin internet ni costos): compone la respuesta con frases
  literales de la base de conocimiento autorizada, por lo que no puede alucinar contenido.
- Modo "llm" (opcional): si hay ANTHROPIC_API_KEY, Claude redacta la respuesta usando SOLO
  los artículos recuperados. Ante cualquier error se regresa al modo extractivo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.preprocessing import split_sentences
from app.services.retriever import RetrievedArticle

logger = logging.getLogger("acn.generator")

ESCALATION_NOTE = (
    "Por la naturaleza de su caso, lo canalizaré de inmediato con el área especializada de NexaBank, "
    "que dará seguimiento con un número de folio."
)
NO_CONTEXT_REPLY = (
    "No encontré información suficiente en la base de conocimiento autorizada para responder esta consulta. "
    "Le pido un momento para validarlo con el área correspondiente."
)

SYSTEM_PROMPT = (
    "Eres el Asistente Cognitivo de NexaBank. Redactas un BORRADOR de respuesta que un agente humano del "
    "centro de contacto revisará antes de enviarlo al cliente. Usa exclusivamente la información de los "
    "artículos proporcionados; si no alcanza, dilo. No inventes montos, plazos ni políticas. No solicites "
    "NIP, contraseñas ni códigos. Responde en español, en tono cordial y profesional, en un máximo de 90 palabras, "
    "sin saludos largos y sin incluir los identificadores de los artículos."
)


@dataclass(frozen=True)
class Generation:
    text: str
    mode: str  # "extractivo" | "llm" | "extractivo_fallback"


def extractive_answer(retrieved: list[RetrievedArticle], escalate: bool) -> str:
    if not retrieved:
        return NO_CONTEXT_REPLY
    top = retrieved[0].article
    # Se usa la respuesta aprobada del artículo; si no existe, las dos primeras frases de la política.
    body = top.customer_reply or " ".join(split_sentences(top.content)[:2])
    opener = "" if body.startswith("Gracias") else "Gracias por comunicarse con NexaBank."
    parts = [p for p in (opener, body) if p]
    if escalate and top.category in ("posible_fraude", "queja_servicio"):
        return " ".join(parts)  # la respuesta aprobada de estos artículos ya incluye la canalización
    if escalate:
        parts.append(ESCALATION_NOTE)
    return " ".join(parts)


class ResponseGenerator:
    def __init__(self, llm_enabled: bool = False, model: str = "claude-opus-5-5", timeout_s: float = 20.0):
        self.llm_enabled = llm_enabled
        self.model = model
        self._client = None
        if llm_enabled:
            try:
                import anthropic

                self._client = anthropic.Anthropic(timeout=timeout_s, max_retries=1)
            except Exception:  # dependencia o credencial ausente: se opera en modo extractivo
                logger.exception("No se pudo inicializar el cliente de Claude; se usará el modo extractivo")
                self.llm_enabled = False

    @property
    def mode(self) -> str:
        return "llm" if self.llm_enabled else "extractivo"

    def generate(self, customer_message: str, retrieved: list[RetrievedArticle], escalate: bool) -> Generation:
        if not self.llm_enabled or not retrieved:
            return Generation(extractive_answer(retrieved, escalate), "extractivo")
        try:
            return Generation(self._generate_llm(customer_message, retrieved, escalate), "llm")
        except Exception as exc:  # cualquier falla del proveedor no debe tumbar el servicio
            logger.warning("Fallo en generación LLM (%s); se usa respuesta extractiva", type(exc).__name__)
            return Generation(extractive_answer(retrieved, escalate), "extractivo_fallback")

    def _generate_llm(self, customer_message: str, retrieved: list[RetrievedArticle], escalate: bool) -> str:
        context = "\n\n".join(f"<articulo titulo=\"{r.article.title}\">\n{r.article.content}\nRespuesta aprobada: {r.article.customer_reply}\n</articulo>" for r in retrieved)
        instruction = "Indica que el caso se canalizará con el área especializada." if escalate else ""
        response = self._client.beta.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{
                "role": "user",
                "content": f"Artículos autorizados:\n{context}\n\nMensaje del cliente (datos sensibles enmascarados):\n{customer_message}\n\n{instruction}",
            }],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("El modelo declinó la solicitud")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise RuntimeError("Respuesta vacía del modelo")
        return text
