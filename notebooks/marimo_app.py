import marimo as mo

# Initialize the notebook application
app = mo.App(width="medium", css_file="marimo_app.css")


@app.cell
def imports():
    # Import necessary packages within a cell
    import altair as alt
    import marimo as mo
    import numpy as np
    import pandas as pd

    return np, pd, alt, mo


@app.cell
def generate_data(np, pd):
    # Generate dummy data for the dashboard
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=100)
    df = pd.DataFrame(
        {
            "Date": dates,
            "Product_A": np.random.randn(100).cumsum() + 50,
            "Product_B": np.random.randn(100).cumsum() + 40,
            "Product_C": np.random.randn(100).cumsum() + 30,
        }
    )
    return dates, df


@app.cell
def create_widgets():
    # Create reactive widgets using marimo's native UI elements
    product_selector = mo.ui.dropdown(
        options=["Product_A", "Product_B", "Product_C"],
        value="Product_A",
        label="Select Product Line",
    )

    window_slider = mo.ui.slider(start=1, stop=20, step=1, value=5, label="Moving Average Window (Days)")
    return product_selector, window_slider


@app.cell
def generate_plots(df, product_selector, window_slider, alt):
    # Fetch the state values currently selected in the widgets
    product = product_selector.value
    window = window_slider.value

    # --- TAB 1: Trend Plot Generation ---
    # Prepare smoothed data
    plot_df = df[["Date", product]].copy()
    plot_df["Smoothed"] = df[product].rolling(window=window, min_periods=1).mean()

    # Raw data line (gray, low opacity)
    raw_line = (
        alt.Chart(plot_df)
        .mark_line(color="gray", opacity=0.3)
        .encode(x=alt.X("Date:T", title="Timeline"), y=alt.Y(f"{product}:Q", title="Units Sold"))
    )

    # Smoothed moving average line (blue, thick)
    smoothed_line = (
        alt.Chart(plot_df)
        .mark_line(color="#1f77b4", strokeWidth=2.5)
        .encode(x=alt.X("Date:T", title="Timeline"), y=alt.Y("Smoothed:Q", title="Units Sold"))
    )

    chart1 = (
        (raw_line + smoothed_line)
        .properties(title=f"Sales Trend Analysis for {product}", width=800, height=400)
        .configure_title(fontSize=14, fontWeight="bold")
    )

    # --- TAB 2: Performance Summary Statistics Generation ---
    summary_data = df[[product]].describe().drop("count").reset_index()
    summary_data.columns = ["Statistic", "Value"]

    chart2 = (
        alt.Chart(summary_data)
        .mark_bar()
        .encode(
            x=alt.X("Statistic:N", title=None, sort=None),
            y=alt.Y("Value:Q", title="Value Scale"),
            color=alt.Color("Statistic:N", legend=None),
        )
        .properties(title=f"Performance Metrics Summary: {product}", width=800, height=400)
        .configure_title(fontSize=14, fontWeight="bold")
    )

    return chart1, chart2


@app.cell
def build_and_render_layout(chart1, chart2, product_selector, window_slider):
    # Define a clean sidebar column for settings
    sidebar = mo.vstack(
        [
            mo.md("## Configurationnn"),
            mo.md("Adjust parameters below to filter and smooth the timeline data."),
            product_selector,
            window_slider,
        ],
        gap=1.5,
    ).style(
        {
            "background-color": "#f8f9fa",
            "padding": "20px",
            "border-radius": "8px",
        }
    )

    # Wrap the generated plots into interactive tab elements
    tabs = mo.ui.tabs(
        {
            "📈 Sales Trend": mo.ui.altair_chart(chart1),
            "📊 Data Summary": mo.ui.altair_chart(chart2),
        }
    )

    # Construct the final main dashboard view area
    main_content = mo.vstack(
        [
            mo.md("# 📈 Corporate Sales Performance Dashboard"),
            mo.md("This standalone interactive application runs entirely reactive on native marimo structures."),
            tabs,
        ]
    )

    # Use a horizontal layout split to position the sidebar next to the content tabs
    dashboard = mo.hstack([sidebar, main_content], widths=[1, 3], gap=2)

    # Flush the assembled dashboard layout straight onto the web page interface
    return dashboard, main_content, sidebar, tabs


if __name__ == "__main__":
    app.run()
