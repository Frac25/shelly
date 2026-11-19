"""Accès local minimal à l'API HTTP Shelly (GET seulement)."""
import ipaddress
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ShellyConnectionError(Exception):
    """Une lecture HTTP ou JSON a échoué."""


def validate_local_host(host):
    """Refuse toute IP publique : ce diagnostic cible le réseau local uniquement."""
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError as exc:
        raise ValueError("Adresse IPv4 invalide : {}".format(host)) from exc
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast:
        raise ValueError("Adresse IP non autorisée (IPv4 privée attendue) : {}".format(host))
    return str(address)


def get_json(host, path, params=None, timeout=6):
    """Requête GET sur un Shelly; n'invoque aucune méthode de modification."""
    host = validate_local_host(host)
    if path not in ("/shelly", "/rpc/Shelly.GetStatus", "/rpc/EM1Data.GetRecords"):
        raise ValueError("Endpoint non autorisé : {}".format(path))
    url = "http://{}{}".format(host, path)
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "ShellyCollector-Diagnostic/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            # Diagnostic: limiter la réponse à 2 Mo; le téléchargement des séries sera ajouté plus tard.
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ShellyConnectionError("Réponse trop volumineuse")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ShellyConnectionError("La réponse JSON n'est pas un objet")
        return data
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShellyConnectionError(str(exc)) from exc
