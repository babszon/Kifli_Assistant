#!/usr/bin/env python3
"""
Beszelgeto motor: Gemini es OpenAI, ugyanazzal a felulettel.

A ket szolgaltato tool calling formatuma kulonbozik, ezert mindegyik
sajat elozmeny-formatumot vezet. Kifele viszont ugyanaz a hivas:

    motor = motor_valaszt()          # a kornyezeti valtozokbol
    valasz = motor.beszelget("tejet kerek", asszisztens)

Ujraprobalkozas: a 429 (tul sok keres), 500, 502, 503 es 504 atmeneti
hibak, ezekre var es ujra probal. A tobbi hiba azonnal visszajon.
"""

import json
import os
import time
import urllib.error
import urllib.request

ATMENETI_HIBAK = {429, 500, 502, 503, 504}
VARAKOZAS = (2, 5, 12)  # masodperc az 1., 2. es 3. ujraprobalkozas elott


class MotorHiba(Exception):
    pass


def _kuld(url, payload, fejlecek, timeout=180):
    """HTTP POST ujraprobalkozassal atmeneti hibak eseten."""
    utolso = None
    for probalkozas in range(len(VARAKOZAS) + 1):
        keres = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers=fejlecek, method="POST")
        try:
            with urllib.request.urlopen(keres, timeout=timeout) as v:
                return json.loads(v.read().decode("utf-8"))
        except urllib.error.HTTPError as h:
            test = h.read().decode("utf-8", errors="replace")
            utolso = MotorHiba(f"HTTP {h.code}: {test[:300]}")
            if h.code not in ATMENETI_HIBAK or probalkozas >= len(VARAKOZAS):
                raise utolso
        except urllib.error.URLError as h:
            utolso = MotorHiba(f"Halozati hiba: {h}")
            if probalkozas >= len(VARAKOZAS):
                raise utolso
        except TimeoutError:
            utolso = MotorHiba("Idotullepes.")
            if probalkozas >= len(VARAKOZAS):
                raise utolso

        var = VARAKOZAS[probalkozas]
        print(f"\033[90m  (ujraprobalom {var} mp mulva...)\033[0m")
        time.sleep(var)
    raise utolso


class Motor:
    """Kozos os. Az eszkozlista semleges formatumban jon."""

    def __init__(self, model, rendszerprompt, eszkozok):
        self.model = model
        self.rendszerprompt = rendszerprompt
        self.eszkozok = eszkozok
        self.elozmeny = []

    def beszelget(self, bemenet, asszisztens, max_kor=8):
        """
        Hiba eseten visszaallitja az elozmenyt arra az allapotra, ami a
        hivas elott volt. Enelkul a valasz nelkul maradt felhasznaloi
        uzenet bent ragad, es a kovetkezo korben osszezavarja a modellt.
        """
        mentett = len(self.elozmeny)
        try:
            return self._beszelget(bemenet, asszisztens, max_kor)
        except Exception:
            del self.elozmeny[mentett:]
            raise

    def _beszelget(self, bemenet, asszisztens, max_kor):
        raise NotImplementedError


class GeminiMotor(Motor):
    nev = "gemini"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        kulcs = os.environ.get("GEMINI_API_KEY")
        if not kulcs:
            raise MotorHiba("Hianyzik a GEMINI_API_KEY.")
        self.url = (f"https://generativelanguage.googleapis.com/v1beta/"
                    f"models/{self.model}:generateContent?key={kulcs}")

    def _eszkozok(self):
        return [{"function_declarations": [
            {"name": e["name"], "description": e["description"],
             "parameters": e["parameters"]} for e in self.eszkozok]}]

    def _beszelget(self, bemenet, asszisztens, max_kor):
        self.elozmeny.append({"role": "user", "parts": [{"text": bemenet}]})

        for _ in range(max_kor):
            valasz = _kuld(self.url, {
                "systemInstruction": {"parts": [{"text": self.rendszerprompt}]},
                "contents": self.elozmeny,
                "tools": self._eszkozok(),
                "generationConfig": {"temperature": 0.3},
            }, {"Content-Type": "application/json"})

            jeloltek = valasz.get("candidates") or []
            if not jeloltek:
                return "(nem kaptam valaszt)"

            reszek = jeloltek[0].get("content", {}).get("parts", [])
            self.elozmeny.append({"role": "model", "parts": reszek})

            hivasok = [r["functionCall"] for r in reszek if "functionCall" in r]
            if not hivasok:
                szoveg = " ".join(r["text"] for r in reszek
                                  if "text" in r).strip()
                return szoveg or "(ures valasz)"

            valaszok = []
            for h in hivasok:
                eredmeny = asszisztens.hivas(h["name"], h.get("args", {}))
                valaszok.append({"functionResponse": {
                    "name": h["name"], "response": {"eredmeny": eredmeny}}})
            self.elozmeny.append({"role": "user", "parts": valaszok})

        return "(tul sok korben ragadtam, kerdezz ujra)"


class OpenAIMotor(Motor):
    nev = "openai"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        kulcs = os.environ.get("OPENAI_API_KEY")
        if not kulcs:
            raise MotorHiba("Hianyzik az OPENAI_API_KEY.")
        self.fejlecek = {"Content-Type": "application/json",
                         "Authorization": f"Bearer {kulcs}"}
        self.url = "https://api.openai.com/v1/chat/completions"
        self.elozmeny = [{"role": "system", "content": self.rendszerprompt}]
        self.reasoning_ki = True

    def _eszkozok(self):
        return [{"type": "function", "function": {
            "name": e["name"], "description": e["description"],
            "parameters": e["parameters"]}} for e in self.eszkozok]

    def _beszelget(self, bemenet, asszisztens, max_kor):
        self.elozmeny.append({"role": "user", "content": bemenet})

        for _ in range(max_kor):
            payload = {
                "model": self.model,
                "messages": self.elozmeny,
                "tools": self._eszkozok(),
                "temperature": 0.3,
            }
            # Az ujabb OpenAI modellek alapbol reasoning modban futnak, es
            # abban a /v1/chat/completions vegpont nem engedi a tool callingot.
            # A 'none' kikapcsolja; a regebbi modellek ezt a mezot figyelmen
            # kivul hagyjak, ezert nem kell modellenkent elagazni.
            if self.reasoning_ki:
                payload["reasoning_effort"] = "none"

            try:
                valasz = _kuld(self.url, payload, self.fejlecek)
            except MotorHiba as e:
                # Ha a modell egyaltalan nem ismeri a mezot, ujra a nelkul
                if self.reasoning_ki and "reasoning_effort" in str(e):
                    self.reasoning_ki = False
                    payload.pop("reasoning_effort", None)
                    valasz = _kuld(self.url, payload, self.fejlecek)
                else:
                    raise

            valasztasok = valasz.get("choices") or []
            if not valasztasok:
                return "(nem kaptam valaszt)"

            uzenet = valasztasok[0]["message"]
            self.elozmeny.append(uzenet)

            hivasok = uzenet.get("tool_calls") or []
            if not hivasok:
                return (uzenet.get("content") or "").strip() or "(ures valasz)"

            for h in hivasok:
                fv = h["function"]
                try:
                    argumentumok = json.loads(fv.get("arguments") or "{}")
                except json.JSONDecodeError:
                    argumentumok = {}
                eredmeny = asszisztens.hivas(fv["name"], argumentumok)
                self.elozmeny.append({
                    "role": "tool", "tool_call_id": h["id"],
                    "content": json.dumps({"eredmeny": eredmeny},
                                          ensure_ascii=False),
                })

        return "(tul sok korben ragadtam, kerdezz ujra)"


ALAP_MODELL = {"gemini": "gemini-3.1-flash-lite", "openai": "gpt-5.6-terra"}


def motor_valaszt(rendszerprompt, eszkozok, szolgaltato=None, model=None):
    """
    A szolgaltatot es a modellt a kornyezeti valtozok dontik el:
        LLM_PROVIDER=openai|gemini
        LLM_MODEL=<modellnev>
    Ha nincs megadva, es van OPENAI_API_KEY, az OpenAI-t valasztja.
    """
    szolgaltato = (szolgaltato or os.environ.get("LLM_PROVIDER") or
                   ("openai" if os.environ.get("OPENAI_API_KEY") else "gemini"))
    szolgaltato = szolgaltato.lower()
    model = model or os.environ.get("LLM_MODEL") or ALAP_MODELL.get(szolgaltato)

    if szolgaltato == "openai":
        return OpenAIMotor(model, rendszerprompt, eszkozok)
    if szolgaltato == "gemini":
        return GeminiMotor(model, rendszerprompt, eszkozok)
    raise MotorHiba(f"Ismeretlen szolgaltato: {szolgaltato}")
