const DATA_PATH = "data/kalix_centrum_1rok_monthly_trend.json";

async function main() {
  const meta = document.getElementById("chart-meta");
  const canvas = document.getElementById("trend-chart");

  try {
    const response = await fetch(DATA_PATH);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    const points = payload.points || [];

    if (points.length === 0) {
      meta.textContent = "No trend points found.";
      return;
    }

    const labels = points.map((point) => point.month);
    const values = points.map((point) => point.trend_price_per_sqm);
    const latest = points[points.length - 1];

    meta.textContent = `${points.length} monthly points. Latest trend: ${latest.trend_price_per_sqm} kr/m² (${latest.month}).`;

    new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Trend price per sqm",
            data: values,
            borderColor: "#1b5e20",
            backgroundColor: "rgba(27, 94, 32, 0.08)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0,
            stepped: true,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
        plugins: {
          legend: {
            display: false,
          },
          tooltip: {
            callbacks: {
              label(context) {
                return `${context.parsed.y} kr/m²`;
              },
            },
          },
        },
        scales: {
          x: {
            ticks: {
              maxTicksLimit: 14,
            },
          },
          y: {
            title: {
              display: true,
              text: "kr/m²",
            },
          },
        },
      },
    });
  } catch (error) {
    meta.textContent = `Could not load chart data: ${error.message}`;
  }
}

main();
