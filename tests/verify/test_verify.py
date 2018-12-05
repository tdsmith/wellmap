#!/usr/bin/env python3

import bio96
import pytest
from pathlib import Path

# These tests are pretty minimal.  Mostly just testing either that it doesn't 
# crash or that it crashes with the right error.  The resulting images are 
# written out as *.pdf files, so you can look at those by hand if you want to 
# be sure the plots are correct (which is *not* tested).

DIR = Path(__file__).parent

def run_cli(args, out='Layout written'):
    import sys, re, shlex, subprocess as proc
    from nonstdlib import capture_output
    from contextlib import contextmanager

    @contextmanager
    def spoof_argv(*args):
        try:
            orig_argv = sys.argv
            sys.argv = args
            yield
        finally:
            sys.argv = orig_argv

    with capture_output() as capture:
        with spoof_argv('bio96', '-o', '$.pdf', *shlex.split(str(args))):
            bio96.verify.main()

        if out is None:
            return
        if isinstance(out, str):
            out = [out]
        for expected in out:
            assert re.search(expected, capture.stdout)


def test_no_wells():
    run_cli(DIR/'no_wells.toml', [
        'no_wells.toml',
        "No wells defined",
    ])

def test_no_attr():
    run_cli(DIR/'no_attrs.toml', "No attributes defined.")

def test_degenerate_attr():
    run_cli(DIR/'degenerate_attr.toml', [
        'degenerate attributes',
        ': x',
    ])

def test_unknown_attr():
    run_cli(f'{DIR}/one_attr.toml XXX', [
        'one_attr.toml',
        "No such attribute: XXX",
        "Did you mean: x",
    ])

    # Make sure the fancy plural logic works :-)
    run_cli(f'{DIR}/one_attr.toml XXX YYY', [
        'one_attr.toml',
        "No such attributes: XXX, YYY",
        "Did you mean: x",
    ])

def test_one_attr():
    run_cli(DIR/'one_attr.toml')

def test_two_attrs():
    run_cli(DIR/'two_attrs.toml')

def test_user_attr():
    run_cli(f'{DIR}/two_attrs.toml x')
    run_cli(f'{DIR}/two_attrs.toml y')
    run_cli(f'{DIR}/two_attrs.toml x y')

def test_skip_wells():
    run_cli(DIR/'skip_wells.toml')

def test_long_labels():
    run_cli(DIR/'long_labels.toml')

def test_reasonably_complex():
    run_cli(DIR/'reasonably_complex_2.toml')
    run_cli(DIR/'reasonably_complex_1.toml')
