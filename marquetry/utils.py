import os
import subprocess
import urllib.request

import numpy as np
import pandas as pd
from PIL import Image

import marquetry
from marquetry import as_variable
from marquetry import Variable


# ===========================================================================
# Visualize for computational graph
# ===========================================================================
def _dot_var(v, verbose=False):
    dot_var = '{} [label="{}", color=orange, style=filled]\n'

    name = "" if v.name is None else v.name
    if verbose and v.data is not None:
        if v.name is not None:
            name += ": "
        name += str(v.shape) + " " + str(v.dtype)

    return dot_var.format(id(v), name)


def _dot_func(f):
    dot_func = '{} [label="{}", color=lightblue, style=filled, shape=box]\n'
    ret = dot_func.format(id(f), f.__class__.__name__)

    dot_edge = '{} -> {}\n'
    for x in f.inputs:
        ret += dot_edge.format(id(x), id(f))
    for y in f.outputs:
        ret += dot_edge.format(id(f), id(y()))

    return ret


def get_dot_graph(output, verbose=True):
    """Generates a graphviz DOT text of a computational graph.

    Build a graph of functions and variables backward-reachable from the output.
    To visualize a graphviz DOT text, you need the dot binary from the graph viz
    package (www.graphviz.org).
    """
    txt = ""
    funcs = []
    seen_set = set()

    def add_func(f):
        if f not in seen_set:
            funcs.append(f)
            seen_set.add(f)

    add_func(output.creator)
    txt += _dot_var(output, verbose)

    while funcs:
        func = funcs.pop()
        txt += _dot_func(func)
        for x in func.inputs:
            txt += _dot_var(x, verbose)

            if x.creator is not None:
                add_func(x.creator)

    return 'digraph g {\n' + txt + "}"


def plot_dot_graph(output, verbose=True, to_file="graph.png"):
    dot_graph = get_dot_graph(output, verbose)

    tmp_dir = os.path.join(os.path.expanduser("~"), ".module_tmp")
    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)

    graph_path = os.path.join(tmp_dir, "tmp_graph.dot")

    with open(graph_path, "w") as f:
        f.write(dot_graph)

    extension = os.path.splitext(to_file)[1][1:]
    cmd = 'dot {} -T {} -o {}'.format(graph_path, extension, to_file)
    subprocess.run(cmd, shell=True)

    img = Image.open(to_file)
    img.show()


# ===========================================================================
# utility functions for numpy calculation
# ===========================================================================
def sum_to(x, shape):
    """Sum elements along axes to output an array of a given shape."""
    ndim = len(shape)
    lead = x.ndim - ndim
    lead_axis = tuple(range(lead))

    axis = tuple([i + lead for i, sx in enumerate(shape) if sx == 1])
    y = x.sum(lead_axis + axis, keepdims=True)
    if lead > 0:
        y = y.squeeze(lead_axis)
    return y


def reshape_sum_backward(grad_y, x_shape, axis, keepdims):
    """Reshape gradient appropriately for sum's backward."""
    ndim = len(x_shape)
    tupled_axis = axis
    if axis is None:
        tupled_axis = None
    elif not isinstance(axis, tuple):
        tupled_axis = (axis,)

    if not (ndim == 0 or tupled_axis is None or keepdims):
        actual_axis = [a if a >= 0 else a + ndim for a in tupled_axis]
        shape = list(grad_y.shape)
        for a in sorted(actual_axis):
            shape.insert(a, 1)
    else:
        shape = grad_y.shape

    grad_y = grad_y.reshape(shape)
    return grad_y


def logsumexp(x, axis=1):
    x_max = x.max(axis=axis, keepdims=True)
    y = x - x_max
    np.exp(y, out=y)
    sum_exp = y.sum(axis=axis, keepdims=True)
    np.log(sum_exp, out=sum_exp)
    y = x_max + sum_exp

    return y


def max_backward_shape(x, axis):
    if axis is None:
        axis = range(x.ndim)
    elif isinstance(axis, int):
        axis = (axis,)
    else:
        axis = axis

    shape = [s if ax not in axis else 1 for ax, s in enumerate(x.shape)]

    return shape


# ===========================================================================
# Download utilities
# ===========================================================================
def show_progress(block_num, block_size, total_size):
    bar_template = "\r[{}] {:.2f}%"

    downloaded = block_num * block_size
    percent = downloaded / total_size * 100
    indicator_num = int(downloaded / total_size * 30)

    percent = percent if percent < 100. else 100.
    indicator_num = indicator_num if indicator_num < 30 else 30

    indicator = "#" * indicator_num + "." * (30 - indicator_num)
    print(bar_template.format(indicator, percent), end="")


def get_file(url, file_name=None):
    if file_name is None:
        file_name = url[url.rfind("/") + 1:]

    file_path = os.path.join(marquetry.Config.CACHE_DIR, file_name)

    if not os.path.exists(marquetry.Config.CACHE_DIR):
        os.mkdir(marquetry.Config.CACHE_DIR)

    if os.path.exists(file_path):
        return file_path

    print("Downloading: " + file_name)

    try:
        urllib.request.urlretrieve(url, file_path, show_progress)

    except (Exception, KeyboardInterrupt):
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    print(" Done")

    return file_path


# ===========================================================================
# Gradient check
# ===========================================================================
def gradient_check(f, x, *args, rtol=1e-4, atol=1e-5, **kwargs):
    x = as_variable(x)
    x.data = x.data.astype(np.float64)

    num_grad = numerical_grad(f, x, *args, **kwargs)
    y = f(x, *args, **kwargs)
    y.backward()
    bp_grad = x.grad.data

    assert bp_grad.shape == num_grad.shape
    res = array_close(num_grad, bp_grad, rtol=rtol, atol=atol)

    grad_diff = np.abs(bp_grad - num_grad).sum()
    if not res:
        print("")
        print("========== FAILED (Gradient Check) ==========")
        print("Back propagation for {} failed.".format(f.__class__.__name__))
        print("Grad Diff: {}".format(grad_diff))
        print("=============================================")
    else:
        print("")
        print("========== OK (Gradient Check) ==========")
        print("Grad Diff: {}".format(grad_diff))
        print("=============================================")

    return res


def numerical_grad(func, x, *args, **kwargs):
    eps = 1e-4

    x = x.data if isinstance(x, Variable) else x
    np_x = x

    grad = np.zeros_like(x)

    iters = np.nditer(np_x, flags=["multi_index"], op_flags=["readwrite"])
    while not iters.finished:
        index = iters.multi_index
        tmp_val = x[index].copy()

        x[index] = tmp_val + eps
        y1 = func(x, *args, **kwargs)
        if isinstance(y1, Variable):
            y1 = y1.data

        y1 = y1.copy()

        x[index] = tmp_val - eps
        y2 = func(x, *args, **kwargs)
        if isinstance(y2, Variable):
            y2 = y2.data

        y2 = y2.copy()

        if isinstance(y1, list):
            diff = 0
            for i in range(len(y1)):
                diff += (y1[i] - y2[i]).sum()
        else:
            diff = (y1 - y2).sum()

        if isinstance(diff, Variable):
            diff = diff.data

        grad[index] = diff / (2 * eps)

        x[index] = tmp_val
        iters.iternext()

    return grad


def array_equal(a, b):
    a = a.data if isinstance(a, Variable) else a
    b = b.data if isinstance(b, Variable) else b

    return np.array_equal(a, b)


def array_close(a, b, rtol=1e-4, atol=1e-5):
    a = a.data if isinstance(a, Variable) else a
    b = b.data if isinstance(b, Variable) else b

    a, b = np.array(a), np.array(b)

    return np.allclose(a, b, rtol, atol)


# ===========================================================================
# data preprocess
# ===========================================================================
def label_encoder(data: pd.DataFrame, target_columns: list):
    if len(target_columns) == 0:
        return data

    replace_dict = {}

    for target_column in target_columns:
        tmp_series = data[target_column]
        unique_set = list(set(tmp_series))
        class_set = list(range(len(unique_set)))

        tmp_dict = dict(zip(unique_set, class_set))

        replace_dict[target_column] = tmp_dict

    return data.replace(replace_dict), replace_dict


def data_normalizer(data: pd.DataFrame, target_columns: list):
    if len(target_columns) == 0:
        return data


