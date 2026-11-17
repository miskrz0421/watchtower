"""Reports over the history: pandas tables and matplotlib charts.

Needs the `reports` extra (pandas, matplotlib); the core never imports this
package (see ADR-003).
"""

from watchtower.reports._charts import save_charts
from watchtower.reports._tables import changes_per_week, failure_rate, price_trend

__all__ = ["changes_per_week", "failure_rate", "price_trend", "save_charts"]
