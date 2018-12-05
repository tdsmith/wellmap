#!/usr/bin/env python3

"""\
Usage:
    bio96 <toml> [<attr>...] [options]

Arguments:
    <toml>
        TOML file describing the plate layout to display.  For a complete 
        description of the file format, refer to:
        
        https://github.com/kalekundert/bio96/

    <attr>
        The name(s) of one or more attributes from the above TOML file to 
        project onto the plate.  For example, if the TOML file contains 
        something equivalent to `well.A1.conc = 1`, then "conc" would be a 
        valid attribute.

Options:
    -o --output PATH
        Output an image of the layout to the given path.  The file type is 
        inferred from the file extension.

    -c --color NAME  [default: rainbow]
        Use the given color scheme to illustrate which wells have which 
        properties.  The given NAME must be one of the color scheme names 
        understood by either `matplotlib` or `colorcet`.  See the links below 
        for the full list of supported colors, but some common choices are:

        rainbow:  blue, green, yellow, red
        viridis:  purple, green, yellow
        plasma:   purple, red, yellow
        coolwarm: blue, red

        Matplotlib colors:
        https://matplotlib.org/examples/color/colormaps_reference.html

        Colorcet colors:
        http://colorcet.pyviz.org/

    -f --foreground
        Don't attempt to return the terminal to the user while the GUI runs.  
        This is meant to be used on systems where the program crashes if run in 
        the background.
"""

import bio96
import colorcet
import numpy as np
import matplotlib.pyplot as plt
import sys, os

from bio96 import ConfigError
from nonstdlib import plural
from matplotlib.colors import BoundaryNorm, Normalize
from pathlib import Path

CELL_SIZE = 0.25
PAD_WIDTH = 0.20
PAD_HEIGHT = 0.20
BAR_WIDTH = 0.15
BAR_PAD_WIDTH = PAD_WIDTH
TOP_MARGIN = 0.5
LEFT_MARGIN = 0.5
RIGHT_MARGIN = PAD_WIDTH
BOTTOM_MARGIN = PAD_HEIGHT

# TODO:
# - General renaming/refactoring
# - Object for num plates/attrs/rows/cols
# - Tests?

def main():
    import docopt

    try:
        args = docopt.docopt(__doc__)
        toml_path = Path(args['<toml>'])

        df = bio96.load(toml_path)
        cmap = colorcet.cm.get(args['--color'], plt.get_cmap(args['--color']))

        if not args['--foreground'] and not args['--output']:
            if os.fork() != 0:
                sys.exit()

        fig = plot_attrs(df, args['<attr>'], cmap=cmap)

        if args['--output']:
            out_path = args['--output'].replace('$', toml_path.stem)
            fig.savefig(out_path)
            print("Layout written to:", out_path)
        else:
            plt.show()

    except CliError as err:
        print(err)
    except ConfigError as err:
        err.toml_path = toml_path
        print(err)


def plot_attrs(df, user_attrs, cmap):
    import matplotlib.pyplot as plt

    # The whole architecture of this program is dictated by a small and obscure 
    # bug in matplotlib.  (Well, I think it's a bug.)  That bug is: if you are 
    # displaying a figure in the GUI and you use `set_size_inches()`, the whole 
    # GUI will have the given height, but the figure itself will be too short 
    # by the height of the GUI control panel.  That control panel has different 
    # heights with different backends (and no way that I know of to query what 
    # it's height will be), so `set_size_inches()` is not reliable.
    #
    # The only way to reliably control the height of the figure is to provide a 
    # size when constructing it.  But that requires knowing the size of the 
    # figure in advance.  I would've preferred to set the size at the end, 
    # because by then I know everything that will be in the figure.  Instead, I 
    # have to basically work out some things twice (once to figure out how big 
    # they will be, then a second time to actually put them in the figure).
    #
    # In particular, I have to work out the colorbar labels twice.  These are 
    # the most complicated part of the figure layout, because they come from 
    # the TOML file and could be either very narrow or very wide.  So I need to 
    # do a first pass where I plot all the labels on a dummy figure, get their 
    # widths, then allocate enough room for them in the main figure.  I also 
    # need to work out the dimensions of the plates twice, but that's a simpler 
    # calculation.

    if 'plate' not in df:
        df.insert(0, 'plate', '')

    plates = sorted(df['plate'].unique())
    attrs = pick_attrs(df, user_attrs)

    fig, axes = setup_axes(df, plates, attrs)

    for i, attr in enumerate(attrs):
        norm = pick_norm(axes[i,-1], df, attr, cmap)

        for j, plate in enumerate(plates):
            plot_plate(axes[i,j], df, plate, attr, norm, cmap)

    for i, attr in enumerate(attrs):
        axes[i,0].set_ylabel(attr)
    for j, plate in enumerate(plates):
        axes[0,j].set_xlabel(plate)
        axes[0,j].xaxis.set_label_position('top')

    for ax in axes[1:,:-1].flat:
        ax.set_xticklabels([])
    for ax in axes[:,1:-1].flat:
        ax.set_yticklabels([])

    return fig

def pick_attrs(df, user_attrs):
    bio96_cols = ['plate', 'well', 'well0', 'row', 'col', 'row_i', 'col_j', 'path']
    user_cols = [x for x in df.columns if x not in bio96_cols]

    if user_attrs:
        # Complain if the user specified any columns that don't exist.

        # Using lists (slower) instead of sets (faster) to maintain the order 
        # of the attributes in case we want to print an error message.
        unknown_attrs = [
                x for x in user_attrs
                if x not in user_cols
        ]
        if unknown_attrs:
            raise ConfigError(f"No such {plural(unknown_attrs):attribute/s}: {', '.join(unknown_attrs)}.\n\nDid you mean: {', '.join(user_cols)}")

        return user_attrs

    # If the user didn't specify any columns, show any that have more than one 
    # unique value.
    else:
        degenerate_cols = [
                x for x in user_cols
                if df[x].nunique() == 1
        ]
        non_degenerate_cols = [
                x for x in user_cols
                if x not in degenerate_cols
        ]
        if not non_degenerate_cols:
            if degenerate_cols:
                raise CliError(f"Found only degenerate attributes (i.e. with the same value in every well): {', '.join(degenerate_cols)}")
            else:
                raise ConfigError(f"No attributes defined.")

        return non_degenerate_cols

def pick_norm(ax, df, attr, cmap):
    from matplotlib.colorbar import ColorbarBase

    norm = SortNorm(df[attr].unique())

    bar = ColorbarBase(
            ax,
            norm=norm.norm,
            cmap=cmap,
            boundaries=norm.boundaries,
    )

    bar.set_ticks(list(norm.map.values()))
    bar.set_ticklabels(list(norm.map.keys()))

    ax.invert_yaxis()


    return norm

def plot_plate(ax, df, plate, attr, norm, cmap):
    i0 = df['row_i'].min()
    j0 = df['col_j'].min() 
    num_rows = df['row_i'].max() - i0 + 1
    num_cols = df['col_j'].max() - j0 + 1

    q = df.query('plate == @plate')

    matrix = np.full((num_rows, num_cols), np.nan)
    for _, well in q.iterrows():
        i = well['row_i'] - i0
        j = well['col_j'] - j0
        matrix[i, j] = norm(well[attr])

    ax.matshow(matrix, norm=norm.norm, cmap=cmap)

    xticks = np.arange(num_cols)
    xticklabels = [bio96.col_from_j(j + j0) for j in xticks]
    yticks = np.arange(num_rows)
    yticklabels = [bio96.row_from_i(i + i0) for i in yticks]

    ax.set_xticks(xticks)
    ax.set_yticks(yticks)
    ax.set_xticks(xticks - 0.5, minor=True)
    ax.set_yticks(yticks - 0.5, minor=True)
    ax.set_xticklabels(xticklabels)
    ax.set_yticklabels(yticklabels)
    ax.grid(which='minor')
    ax.tick_params(which='both', axis='both', length=0)


def setup_axes(df, plates, attrs):
    from mpl_toolkits.axes_grid1 import Divider
    from mpl_toolkits.axes_grid1.axes_size import Fixed

    # These assumptions let us simplify some code, and should always be true.
    assert len(plates) > 0
    assert len(attrs) > 0

    # Determine how much data will be shown in the figure:
    num_plates = len(plates)
    num_attrs = len(attrs)
    num_rows = df['row_i'].max() - df['row_i'].min() + 1
    num_cols = df['col_j'].max() - df['col_j'].min() + 1

    bar_label_width = guess_attr_label_width(df, attrs)

    # Define the grid on which the axes will live:
    h_divs  = [
            LEFT_MARGIN,
    ]
    for _ in plates:
        h_divs += [
                CELL_SIZE * num_cols,
                PAD_WIDTH,
        ]
    h_divs[-1:] = [
            BAR_PAD_WIDTH,
            BAR_WIDTH,
            RIGHT_MARGIN + bar_label_width,
    ]

    v_divs = [
            TOP_MARGIN,
    ]
    for _ in attrs:
        v_divs += [
                CELL_SIZE * num_rows,
                PAD_HEIGHT,
        ]
    v_divs[-1:] = [
            BOTTOM_MARGIN,
    ]

    # Add up all the divisions to get the width and height of the figure:
    figsize = sum(h_divs), sum(v_divs)

    # Make the figure:
    fig, axes = plt.subplots(
            num_attrs,
            num_plates + 1,  # +1 for the colorbar axes.
            figsize=figsize,
            squeeze=False,
    )

    # Position the axes:
    rect = 0.0, 0.0, 1, 1
    h_divs = [Fixed(x) for x in h_divs]
    v_divs = [Fixed(x) for x in reversed(v_divs)]
    divider = Divider(fig, rect, h_divs, v_divs, aspect=False)

    for i in range(num_attrs):
        for j in range(num_plates + 1):
            loc = divider.new_locator(nx=2*j+1, ny=2*(num_attrs - i) - 1)
            axes[i,j].set_axes_locator(loc)

    return fig, axes

def guess_attr_label_width(df, attrs):
    # I've seen some posts suggesting that this might not work on Macs.  I 
    # can't test that, but if this ends up being a problem, I probably need to 
    # wrap this is a try/except block and fall back to guessing a width based 
    # on the number of characters in the string representation of each label.

    width = 0
    fig, ax = plt.subplots()

    for attr in attrs:
        labels = df[attr].unique()
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)

        width = max(width, get_yticklabel_width(fig, ax))

    plt.close(fig)
    return width

def get_yticklabel_width(fig, ax):

    # With some backends, getting the renderer like this may trigger a warning 
    # and cause matplotlib to drop down to the Agg backend.
    from matplotlib import tight_layout
    renderer = tight_layout.get_renderer(fig)

    width = max(
            artist.get_window_extent(renderer).width
            for artist in ax.get_yticklabels()
    )
    dpi = ax.get_figure().get_dpi()

    return width / dpi

# Bad name...
class SortNorm:

    def __init__(self, values):
        self.map = {x: i for i, x in enumerate(values) if not self.isnan(x)}

        n = len(self.map)
        self.boundaries = np.arange(n+1) - 0.5
        self.norm = Normalize(vmin=0, vmax=n-1)

    def __call__(self, x, clip=None):
        if self.isnan(x):
            return np.nan
        return self.map[x]

        #from matplotlib.cbook import iterable
        #values = value if iterable(value) else [value]
        #return np.array([self.map[x] for x in values])

    @staticmethod
    def isnan(x):
        return isinstance(x, float) and np.isnan(x)

class CliError(Exception):
    pass
