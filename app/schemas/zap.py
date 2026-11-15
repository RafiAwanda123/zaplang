"""Schema Pydantic untuk data ZAP (alert, scan, dll.).

TODO: Tambah model Alert, ScanStatus, SpiderResult.
"""

from pydantic import BaseModel, Field


class Alert(BaseModel):
    """Representasi satu alert dari ZAP /JSON/alert/view/alerts/.

    Field ini merupakan subset; lengkapi sesuai respons ZAP.
    Semua field string dari ZAP dianggap untrusted (scope: untrusted-output-handling).
    """

    plugin_id: str = Field(alias="pluginId", default="")
    alert: str = ""
    risk: str = ""
    url: str = ""
    evidence: str = ""
    description: str = ""

