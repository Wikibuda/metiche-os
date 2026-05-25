# app/core/roles.py
from app.core.branding import BOT_NAME


class RolesConfig:
    BOT_NAME = BOT_NAME
    owner_name: str = "Gus"
    admin_ids: set[str] = {"gglunar@gmail.com", "gus@masamadremonterrey.com"}

    @property
    def owner_display(self) -> str:
        return self.owner_name

    def get_role(self, author_email: str) -> str:
        author = (author_email or "").strip().lower()
        if author in {a.strip().lower() for a in self.admin_ids}:
            return "admin"
        return "viewer"

    def can_execute(self, author_email: str, action: str = "") -> bool:
        role = self.get_role(author_email)
        if role == "admin":
            # Admin auto-ejecuta, salvo "encolar FIFO"
            if "encolar" in action.lower() or "fifo" in action.lower():
                return False
            return True
        return False


roles_config = RolesConfig()
