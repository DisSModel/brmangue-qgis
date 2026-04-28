# -*- coding: utf-8 -*-
"""
payload_builder.py
------------------
Builds the JSON payload for POST /submit_job,
matching the DisSModel Platform API contract exactly.
"""

from __future__ import annotations


def build_payload(params: dict) -> dict:
    """
    Build the JSON body for POST /submit_job.

    Mirrors the contract:
        {
            "model_name":    "brmangue",
            "input_dataset": "s3://...",
            "parameters": {
                "end_time":      10,
                "resolution":    100.0,
                "taxa_elevacao": 0.5,
                "altura_mare":   6.0,
                "acrecao_ativa": false
            }
        }

    Parameters
    ----------
    params : dict
        Values collected from BrmangueDialog._collect_params().
    """
    return {
        "model_name":    "brmangue",
        "input_dataset": params["input_uri"],
        "parameters": {
            "end_time":      params["end_time"],
            "resolution":    params.get("resolution", 100.0),
            "taxa_elevacao": params["taxa_elevacao"],
            "altura_mare":   params["altura_mare"],
            "acrecao_ativa": params["acrecao_ativa"],
        },
    }
