# Development notes

## Issues displaying rich content in Jupyter
These cells fail:

```python
import pandas as pd
import itables
from IPython.display import display, HTML, IFrame

display(HTML("<b>hello</b>"))
IFrame('data:text/html,<h1 style="color:red">TEST</h1>', width=400, height=100)

df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
styler = df.style
styler = styler.format("{:.2f}").highlight_max()
styler = styler.
display(df)
display(styler)
itables.show(df)
```

get:

```python
<IPython.core.display.HTML object>
<IPython.lib.display.IFrame object at 0x00000227CEAE6F90>

   A  B    # <-- Unstyled plain text
0  1  3
1  2  4
<pandas.io.formats.style.Styler object at 0x000001AB9F7CA0D0>
<IPython.core.display.HTML object>
```

### Workarounds:

Output raw html. E.g.

```python
import pandas as pd
from itables import JavascriptCode, to_html_datatable
import itables as itables
from IPython.display import display, HTML

# HTML
display({"text/html": HTML("<h1>Hello, world!</h1>").data}, raw=True)

# df
df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
styler = df.style
styler = df.style.format("{:.2f}").highlight_max()
with pd.option_context("display.notebook_repr_html", True):
    display(df)

# Or to display styled df:
display({"text/html": styler.to_html()}, raw=True)

# itables
html_output = to_html_datatable(df, style="table-layout:auto;width:auto;margin:0;caption-side:bottom", caption="This is my table caption")
display({"text/html": html_output}, raw=True)
```

Similarly for matplotlib:

```python
    import matplotlib.pyplot as plt
    import mpld3

    # Workaround:
        import warnings
        # Silence the outdated mplexporter line style parsing warnings from mpld3
        # Scope the warning suppression strictly to this block
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=UserWarning,
                module="mpld3.mplexporter",
            )
            html_string = mpld3.fig_to_html(fig)
        display({"text/html": html_string} , raw=True)
        plt.close(fig) # Cleanup
```

### Proper workaround

Re-register the Text/HTML Formatter

Somehow, third-party libraries accidentally clear out or break IPython's formatter registry.
You can force the notebook backend to hook the HTML repr back up by executing this:

```python
from IPython.core.interactiveshell import InteractiveShell

# Explicitly re-enable mime processing in the active shell formatter
ip = InteractiveShell.instance()
ip.display_formatter.formatters["application/javascript"].enabled = True
ip.display_formatter.formatters["image/jpeg"].enabled = True
ip.display_formatter.formatters["image/png"].enabled = True
ip.display_formatter.formatters["image/svg+xml"].enabled = True
ip.display_formatter.formatters["text/html"].enabled = True
ip.display_formatter.formatters["text/markdown"].enabled = True
```

## Inline matplot lib
```python
# Show matplotlib graphs
%matplotlib inline
%matplotlib ipympl
```
