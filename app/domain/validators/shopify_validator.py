from __future__ import annotations

from app.core.config import settings
from app.domain.validators.base import BaseValidator, ValidationResult


class ShopifyValidator(BaseValidator):
    channel = "shopify"

    def validate(self, task_title: str, task_description: str) -> ValidationResult:
        store_domain = settings.shopify_store_domain
        if not store_domain and settings.shopify_store_url:
            normalized = settings.shopify_store_url.replace("https://", "").replace("http://", "").strip("/")
            store_domain = normalized
        if not store_domain or not settings.shopify_access_token:
            return ValidationResult(
                channel=self.channel,
                passed=False,
                detail="Faltan SHOPIFY_STORE_DOMAIN/SHOPIFY_STORE_URL o SHOPIFY_ACCESS_TOKEN",
                critical=True,
            )
        api_version = settings.shopify_api_version if hasattr(settings, "shopify_api_version") and settings.shopify_api_version else "2024-10"
        url = f"https://{store_domain}/admin/api/{api_version}/shop.json"
        headers = {"X-Shopify-Access-Token": settings.shopify_access_token}
        ok, status, data, err = self._request_json("GET", url, None, headers=headers)
        if ok and data.get("shop"):
            return ValidationResult(channel=self.channel, passed=True, detail="Shopify API accesible", metadata={"status": status, "shop": data.get("shop", {}).get("name")})
        return ValidationResult(channel=self.channel, passed=False, detail=f"Shopify no disponible: {err or data}", critical=True, metadata={"status": status})
