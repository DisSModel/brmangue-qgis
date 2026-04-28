# -*- coding: utf-8 -*-
"""
payload_builder.py
------------------
Builds the JSON payload for POST /submit_job,
matching the DisSModel Platform API contract exactly.
"""

from __future__ import annotations


def build_payload(params: dict) -> dict:
    payload = {
        "model_name":    "brmangue",
        "input_dataset": params["input_uri"],
        "input_format":  params.get("input_format", "auto"),
        "parameters": {
            "end_time":      params["end_time"],
            "resolution":    params.get("resolution", 100.0),
            #"taxa_elevacao": params["taxa_elevacao"],
            #"altura_mare":   params["altura_mare"],
            #"acrecao_ativa": params["acrecao_ativa"],
        },
    }

    # band_map só inclui se o usuário tiver mapeamento customizado
    if params.get("band_map"):
        payload["band_map"] = params["band_map"]

    return payload
