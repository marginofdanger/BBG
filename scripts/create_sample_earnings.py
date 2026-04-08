import json, os
sample = {
  "snapshot_date": "2026-04-06",
  "companies": [
    {
      "ticker": "JPM", "group": "Portfolio",
      "earnings_date": "2026-04-11", "earnings_time": "BMO", "date_confirmed": True,
      "revisions_4wk": {"up": 5, "down": 0},
      "metrics": [
        {"name": "EPS", "consensus": 4.62, "guidance_low": 4.50, "guidance_high": 4.80, "prior_year": 4.12, "yoy": "+12.1%", "vs_guide": "mid"},
        {"name": "Revenue", "consensus": 42800, "guidance_low": 42000, "guidance_high": 43500, "prior_year": 39600, "yoy": "+8.1%", "vs_guide": "mid"},
        {"name": "NII", "consensus": 23100, "guidance_low": 23000, "guidance_high": 23000, "prior_year": 22400, "yoy": "+3.1%", "vs_guide": "above"},
        {"name": "Provisions", "consensus": 2850, "guidance_low": 2600, "guidance_high": 3000, "prior_year": 2410, "yoy": "+18.3%", "vs_guide": "mid"}
      ],
      "annual_metrics": [
        {"name": "EPS", "consensus": 18.75, "guidance_low": 18.00, "guidance_high": 19.50, "prior_year": 17.20, "yoy": "+9.0%", "vs_guide": "mid"}
      ]
    },
    {
      "ticker": "UNH", "group": "Portfolio",
      "earnings_date": "2026-04-10", "earnings_time": "BMO", "date_confirmed": True,
      "revisions_4wk": {"up": 1, "down": 2},
      "metrics": [
        {"name": "EPS", "consensus": 7.29, "guidance_low": 7.05, "guidance_high": 7.45, "prior_year": 6.88, "yoy": "+6.0%", "vs_guide": "mid"},
        {"name": "Revenue", "consensus": 109200, "guidance_low": 108000, "guidance_high": 110000, "prior_year": 99300, "yoy": "+10.0%", "vs_guide": "mid"}
      ],
      "annual_metrics": [
        {"name": "EPS", "consensus": 29.72, "guidance_low": 29.50, "guidance_high": 30.00, "prior_year": 27.80, "yoy": "+6.9%", "vs_guide": "mid"}
      ]
    },
    {
      "ticker": "PGR", "group": "Portfolio",
      "earnings_date": "2026-04-16", "earnings_time": "AMC", "date_confirmed": False,
      "revisions_4wk": {"up": 4, "down": 0},
      "metrics": [
        {"name": "EPS", "consensus": 4.15, "guidance_low": None, "guidance_high": None, "prior_year": 3.40, "yoy": "+22.1%", "vs_guide": "n/a"},
        {"name": "Net Premiums", "consensus": 19800, "guidance_low": None, "guidance_high": None, "prior_year": 16780, "yoy": "+18.0%", "vs_guide": "n/a"},
        {"name": "Combined Ratio", "consensus": 87.5, "guidance_low": None, "guidance_high": None, "prior_year": 89.3, "yoy": "-180bps", "vs_guide": "n/a"}
      ],
      "annual_metrics": []
    },
    {
      "ticker": "TSM", "group": "Portfolio",
      "earnings_date": "2026-04-17", "earnings_time": "BMO", "date_confirmed": True,
      "revisions_4wk": {"up": 7, "down": 0},
      "metrics": [
        {"name": "EPS", "consensus": 2.05, "guidance_low": None, "guidance_high": None, "prior_year": 1.49, "yoy": "+37.6%", "vs_guide": "n/a"},
        {"name": "Revenue", "consensus": 25400, "guidance_low": 25000, "guidance_high": 25800, "prior_year": 18870, "yoy": "+34.6%", "vs_guide": "mid"},
        {"name": "Gross Margin", "consensus": 58.1, "guidance_low": 57.0, "guidance_high": 59.0, "prior_year": 55.5, "yoy": "+260bps", "vs_guide": "mid"},
        {"name": "Op. Margin", "consensus": 47.3, "guidance_low": 46.5, "guidance_high": 48.5, "prior_year": 45.1, "yoy": "+220bps", "vs_guide": "mid"},
        {"name": "Capex", "consensus": 9800, "guidance_low": None, "guidance_high": None, "prior_year": 7000, "yoy": "+40.0%", "vs_guide": "n/a"}
      ],
      "annual_metrics": [
        {"name": "Capex", "consensus": 40200, "guidance_low": 38000, "guidance_high": 42000, "prior_year": 29800, "yoy": "+34.9%", "vs_guide": "mid"}
      ]
    },
    {
      "ticker": "META", "group": "Portfolio",
      "earnings_date": "2026-04-23", "earnings_time": "AMC", "date_confirmed": False,
      "revisions_4wk": {"up": 6, "down": 1},
      "metrics": [
        {"name": "EPS", "consensus": 5.28, "guidance_low": None, "guidance_high": None, "prior_year": 4.59, "yoy": "+15.0%", "vs_guide": "n/a"},
        {"name": "Revenue", "consensus": 41200, "guidance_low": 39500, "guidance_high": 41800, "prior_year": 36155, "yoy": "+14.0%", "vs_guide": "above"},
        {"name": "Op. Margin", "consensus": 38.5, "guidance_low": None, "guidance_high": None, "prior_year": 39.7, "yoy": "-120bps", "vs_guide": "n/a"},
        {"name": "Capex", "consensus": 14500, "guidance_low": None, "guidance_high": None, "prior_year": 9800, "yoy": "+48.0%", "vs_guide": "n/a"}
      ],
      "annual_metrics": [
        {"name": "Capex", "consensus": 62100, "guidance_low": 60000, "guidance_high": 65000, "prior_year": 45000, "yoy": "+38.0%", "vs_guide": "mid"}
      ]
    },
    {
      "ticker": "AMZN", "group": "Portfolio",
      "earnings_date": "2026-04-24", "earnings_time": "AMC", "date_confirmed": False,
      "revisions_4wk": {"up": 8, "down": 1},
      "metrics": [
        {"name": "EPS", "consensus": 1.38, "guidance_low": None, "guidance_high": None, "prior_year": 1.14, "yoy": "+21.1%", "vs_guide": "n/a"},
        {"name": "Revenue", "consensus": 154600, "guidance_low": 151000, "guidance_high": 155500, "prior_year": 140500, "yoy": "+10.0%", "vs_guide": "above"},
        {"name": "Op. Income", "consensus": 16200, "guidance_low": 13000, "guidance_high": 17500, "prior_year": 12650, "yoy": "+28.1%", "vs_guide": "above"},
        {"name": "Capex", "consensus": 24500, "guidance_low": None, "guidance_high": None, "prior_year": 18600, "yoy": "+31.7%", "vs_guide": "n/a"}
      ],
      "annual_metrics": [
        {"name": "Capex", "consensus": 96000, "guidance_low": 100000, "guidance_high": 100000, "prior_year": 72000, "yoy": "+33.3%", "vs_guide": "below"}
      ]
    },
    {
      "ticker": "MSFT", "group": "Watchlist",
      "earnings_date": "2026-04-29", "earnings_time": "AMC", "date_confirmed": True,
      "revisions_4wk": {"up": 5, "down": 2},
      "metrics": [
        {"name": "EPS", "consensus": 3.22, "guidance_low": None, "guidance_high": None, "prior_year": 2.94, "yoy": "+9.5%", "vs_guide": "n/a"},
        {"name": "Revenue", "consensus": 68500, "guidance_low": 67700, "guidance_high": 68700, "prior_year": 61900, "yoy": "+10.7%", "vs_guide": "above"},
        {"name": "Op. Income", "consensus": 30200, "guidance_low": None, "guidance_high": None, "prior_year": 27600, "yoy": "+9.4%", "vs_guide": "n/a"},
        {"name": "Capex", "consensus": 21000, "guidance_low": None, "guidance_high": None, "prior_year": 14000, "yoy": "+50.0%", "vs_guide": "n/a"}
      ],
      "annual_metrics": []
    }
  ]
}
os.makedirs("output/snapshots", exist_ok=True)
with open("output/snapshots/earnings_2026-04-06.json", "w") as f:
    json.dump(sample, f, indent=2)
with open("output/snapshots/index_earnings.json", "w") as f:
    json.dump(["2026-04-06"], f)
print("Sample data written.")
