from __future__ import with_statement, division

__copyright__ = "Copyright (C) 2013 Andreas Kloeckner"

__license__ = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""


import pyopencl as cl
import pyopencl.np as np
from pytools.py_codegen import PythonCodeGenerator, Indentation


def capture_kernel_call(kernel, filename, queue, g_size, l_size, *args, **kwargs):
    try:
        source = kernel._source
    except AttributeError:
        raise RuntimeError("cannot capture call, kernel source not available")

    if source is None:
        raise RuntimeError("cannot capture call, kernel source not available")

    cg = PythonCodeGenerator()

    cg("# generated by pyopencl.capture_call")
    cg("")
    cg("import pyopencl.np as np")
    cg("import pyopencl as cl")
    cg("from base64 import b64decode")
    cg("from zlib import decompress")
    cg("mf = cl.mem_flags")
    cg("")

    cg('CODE = r"""//CL//')
    for l in source.split("\n"):
        cg(l)
    cg('"""')

    # {{{ invocation

    arg_data = []

    cg("")
    cg("")
    cg("def main():")
    with Indentation(cg):
        cg("ctx = cl.create_some_context()")
        cg("queue = cl.CommandQueue(ctx)")
        cg("")

        kernel_args = []

        for i, arg in enumerate(args):
            if isinstance(arg, cl.Buffer):
                buf = bytearray(arg.size)
                cl.enqueue_copy(queue, buf, arg)
                arg_data.append(("arg%d_data" % i, buf))
                cg("arg%d = cl.Buffer(ctx, "
                        "mf.READ_WRITE | cl.mem_flags.COPY_HOST_PTR,"
                        % i)
                cg("    hostbuf=decompress(b64decode(arg%d_data)))"
                        % i)
                kernel_args.append("arg%d" % i)
            elif isinstance(arg, (int, float)):
                kernel_args.append(repr(arg))
            elif isinstance(arg, np.integer):
                kernel_args.append("np.%s(%s)" % (
                    arg.dtype.type.__name__, repr(int(arg))))
            elif isinstance(arg, np.floating):
                kernel_args.append("np.%s(%s)" % (
                    arg.dtype.type.__name__, repr(float(arg))))
            elif isinstance(arg, np.complexfloating):
                kernel_args.append("np.%s(%s)" % (
                    arg.dtype.type.__name__, repr(complex(arg))))
            else:
                try:
                    arg_buf = buffer(arg)
                except:
                    raise RuntimeError("cannot capture: "
                            "unsupported arg nr %d (0-based)" % i)

                arg_data.append(("arg%d_data" % i, arg_buf))
                kernel_args.append("decompress(b64decode(arg%d_data))" % i)

        cg("")

        g_times_l = kwargs.get("g_times_l", False)
        if g_times_l:
            dim = max(len(g_size), len(l_size))
            l_size = l_size + (1,) * (dim-len(l_size))
            g_size = g_size + (1,) * (dim-len(g_size))
            g_size = tuple(
                    gs*ls for gs, ls in zip(g_size, l_size))

        global_offset = kwargs.get("global_offset", None)
        if global_offset is not None:
            kernel_args.append("global_offset=%s" % repr(global_offset))

        cg("prg = cl.Program(ctx, CODE).build()")
        cg("knl = prg.%s" % kernel.function_name)
        if hasattr(kernel, "_arg_type_chars"):
            cg("knl._arg_type_chars = %s" % repr(kernel._arg_type_chars))
        cg("knl(queue, %s, %s," % (repr(g_size), repr(l_size)))
        cg("    %s)" % ", ".join(kernel_args))
        cg("")
        cg("queue.finish()")

    # }}}

    # {{{ data

    from zlib import compress
    from base64 import b64encode
    cg("")
    line_len = 70

    for name, val in arg_data:
        cg("%s = (" % name)
        with Indentation(cg):
            val = str(b64encode(compress(buffer(val))))
            i = 0
            while i < len(val):
                cg(repr(val[i:i+line_len]))
                i += line_len

            cg(")")

    # }}}

    # {{{ file trailer

    cg("")
    cg("if __name__ == \"__main__\":")
    with Indentation(cg):
        cg("main()")
    cg("")

    cg("# vim: filetype=pyopencl")

    # }}}

    with open(filename, "w") as outf:
        outf.write(cg.get())
