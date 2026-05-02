"""
Transforma o AgentContext (Pydantic) em XML estruturado para uso como system prompt.
Chamado no POST /agent e no PUT /agent/context. O resultado é cacheado no Redis
e injetado em cada chamada ao modelo via ai_service.
"""
import xml.etree.ElementTree as ET
from src.routes.base_schemas import AgentContext

def dict_to_xml(parent: ET.Element, data: dict):
    for key, value in data.items():
        child = ET.SubElement(parent, key)
        if isinstance(value, dict):
            dict_to_xml(child, value)
        elif isinstance(value, list):
            for item in value:
                item_el = ET.SubElement(child, "item")
                if isinstance(item, dict):
                    dict_to_xml(item_el, item)
                else:
                    item_el.text = str(item)
        else:
            child.text = str(value)


def build_context_xml(context: AgentContext) -> str:
    root = ET.Element("AgentContext")
    dict_to_xml(root, context.model_dump(exclude_none=True))
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", method="xml")
