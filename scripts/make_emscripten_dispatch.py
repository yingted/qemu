#!/usr/bin/env python

'''
track helper declared types in function pointers

 Copyright (c) 2014 Ted Ying

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public
License as published by the Free Software Foundation; either
version 2 of the License, or (at your option) any later version.

This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with this library; if not, see <http://www.gnu.org/licenses/>.
'''

import sys
import itertools

def main():
    cpp_maxargs = 127
    typebits = 8
    _max_nargs = [None]
    def all_types():
        for nargs in itertools.count():
            for eyes in itertools.product('iq', repeat=nargs):
                for ret in 'viq':
                    yield ret, ''.join(eyes)
            _max_nargs[0] = nargs
    all_types = list(itertools.islice(all_types(), 2**typebits))
    assert len(all_types) == 2**typebits
    max_nargs = _max_nargs[0]
    name = 'QEMU_EMSCRIPTEN_CALL'
    args = 'func,ret'
    arglist = args.split(',')
    protected_args = ','.join('(%s)' % arg for arg in arglist)
    maxcall = cpp_maxargs / 2 - len(arglist) # due to counting trick
    ctype_for = {
        'v': 'void',
        'i': 'int32_t',
        'q': 'tcg_target_long',
    }

    print '''
#ifndef _EMSCRIPTEN_DISPATCH_H_
#define _EMSCRIPTEN_DISPATCH_H_

#include <stdint.h>
#include <assert.h>

typedef enum {
''' % locals()
    for ret, eyes in all_types:
        print '''
    emscripten_func_type_%(ret)s%(eyes)s,
''' % locals()
    print '''
    QEMU_EMSCRIPTEN_FUNC_MAX
} emscripten_func_type;
''' % locals()

    for ret, eyes in all_types:
        types = ','.join(ctype_for[eye] for eye in eyes)
        ret_type = ctype_for[ret]
        print '''
typedef %(ret_type)s (*emscripten_func_%(ret)s%(eyes)s) (%(types)s);
''' % locals()

    print '''

#define QEMU_EMSCRIPTEN_FUNC_TYPE_BITS %(typebits)d
#define QEMU_EMSCRIPTEN_FUNC_PTR_BITS (8 * sizeof(tcg_target_long) - QEMU_EMSCRIPTEN_FUNC_TYPE_BITS)

static inline emscripten_func_type get_emscripten_func_type(
        tcg_target_long em_packed) {
    return ((tcg_target_ulong)em_packed) >> (tcg_target_ulong)QEMU_EMSCRIPTEN_FUNC_PTR_BITS;
}

static inline tcg_target_long get_emscripten_func_ptr(
        tcg_target_long em_packed) {
    return em_packed & (QEMU_EMSCRIPTEN_FUNC_PTR_BITS - 1);
}

static inline tcg_target_long make_emscripten_func_packed(
        tcg_target_long em_ptr, emscripten_func_type type) {
    QEMU_BUILD_BUG_ON((!QEMU_EMSCRIPTEN_FUNC_MAX)
            || (QEMU_EMSCRIPTEN_FUNC_MAX & (QEMU_EMSCRIPTEN_FUNC_MAX - 1)));
    assert(!(type & -QEMU_EMSCRIPTEN_FUNC_MAX));
    assert(!get_emscripten_func_type(em_ptr));
    return em_ptr | (((tcg_target_long)type) << QEMU_EMSCRIPTEN_FUNC_PTR_BITS);
}

static inline emscripten_func_type make_emscripten_func_type(int has_ret,
        int nargs, int sizemask) {
    tcg_target_ulong args_type = 1;
    unsigned args_ret = (tcg_target_ulong)(has_ret ? sizemask & 1 ? 1 : 2 : 3);
    assert(0 <= nargs && nargs < %(max_nargs)s);
    while (nargs--)
        args_type = (args_type << 1) | ((sizemask >>= 2) & 1);
    return args_type * (tcg_target_ulong)3 - args_ret;
}

#if defined(EMSCRIPTEN)
#define %(name)s_CASE(em_arg_type,func,ret,...) \\
        case emscripten_func_type_v ## em_arg_type: \\
            ((emscripten_func_v ## em_arg_type)func)(__VA_ARGS__); \\
            break; \\
        case emscripten_func_type_i ## em_arg_type: \\
            (ret) = ((emscripten_func_i ## em_arg_type)func)(__VA_ARGS__); \\
            break; \\
        case emscripten_func_type_q ## em_arg_type: \\
            (ret) = ((emscripten_func_q ## em_arg_type)func)(__VA_ARGS__); \\
            break; \\
''' % locals()

    print '''
#define %(name)s_CASE_0(func,ret) \\
    %(name)s_CASE(,(func),(ret))

''' % locals()

    prev_extras = eyes = ''
    for i in xrange(1, maxcall):
        prev_i = i - 1
        extras = prev_extras + ',(a%d)' % i
        plain_extras = extras.replace('(', '').replace(')', '')
        print '''
#define %(name)s_CASE_%(i)d(%(args)s%(plain_extras)s) \\
    %(name)s_CASE_%(prev_i)d(%(protected_args)s%(prev_extras)s) \\\
''' % locals()
        for ret, eyes in all_types:
            if ret == 'v' and len(eyes) == i:
                print '''\
    %(name)s_CASE(%(eyes)s,%(protected_args)s%(extras)s) \\\
''' % locals()
        print
        prev_extras = extras

    numbers = ','.join(map(str,reversed(xrange(maxcall))))
    dummies = ''.join('a%d,' % i for i in xrange(len(arglist) - 1 + maxcall))
    print '''
// Usage:
// #define %(name)s_CASE(eyes,%(args)s,...) (my implementation)
// switch(val) %(name)s_CASES(%(args)s,...)
#define %(name)s_CONCAT(x,y) x ## y
#define %(name)s_DISPATCH(x,y) %(name)s_CONCAT(x,y)
#define %(name)s_NARGS(%(dummies)s nargs,...) nargs
#define %(name)s_CASES(...) %(name)s_DISPATCH(%(name)s_CASE_, \\
        %(name)s_NARGS(__VA_ARGS__,%(numbers)s))(__VA_ARGS__)
''' % locals()

    '''
    Emscripten compiles C functions to JS functions and implements function
    pointers as an index in an array of functions with the same declared type.
    This means functions must be casted to more or less the right type at their
    call sites. The built-in implementation doesn't support return type dispatch.
    There are 3 main ways to implement this:
    1. Set ALIASING_FUNCTION_POINTERS=0 and keep a sparse array mapping function
       pointers to their types. This is guaranteed to work.
    2. Track where the function pointers are written in memory and hash the
       addresses to the declared types.
    3. Pack the type into the pointers. This is what this header implements.
    '''

    print '''

#define %(name)s(ctype,func,...) \\
        do { \\
            switch (get_emscripten_func_type((tcg_target_long)(func))) { \\
                %(name)s_CASES((func),__VA_ARGS__) \\
                default: assert(!"Not enough arguments for call to " #func #__VA_ARGS__); \\
            } \\
        } while(0)

#else
#define %(name)s(ctype,%(args)s,...) \\
        do { (ret) = ((ctype)func)(__VA_ARGS__); } while(0)
#endif

#endif
''' % locals()

if __name__ == '__main__':
    main()
