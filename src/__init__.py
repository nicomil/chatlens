"""Pipeline NLP per l'esperimento bargaining_tdl.

Moduli:
- ``text_metrics`` / ``lexicons``: misure deterministiche in stile LIWC-22,
  volume e sentiment. Nessuna dipendenza esterna obbligatoria.
- ``llm_rubric``: seconda misura degli stessi costrutti tramite rubrica
  valutata da Claude, per validazione convergente.
- ``topicgpt``: adattatore per il codice ufficiale di TopicGPT
  (Pham et al., 2024).
- ``aggregate``: aggregazione a coppia ordinata, coppia, partecipante e gruppo,
  e innesto sui dataset dell'esperimento.

Il punto di ingresso è ``run.py`` nella radice del progetto.
"""
