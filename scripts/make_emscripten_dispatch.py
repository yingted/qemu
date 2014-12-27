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

def main():
    maxargs = 127
    typebits = 5
    name = 'QEMU_EMSCRIPTEN_CALL'
    args = 'func,ret'
    arglist = args.split(',')
    protected_args = ','.join('(%s)' % arg for arg in arglist)
    maxcall = maxargs / 2 - len(arglist) # due to counting trick

    print '''
#ifndef _EMSCRIPTEN_DISPATCH_H_
#define _EMSCRIPTEN_DISPATCH_H_
typedef enum {
''' % locals()
    for nr_eyes in xrange(0, 2**(typebits - 1), 1):
        eyes = 'i' * nr_eyes
        print '''
    emscripten_func_v%(eyes)s,
    emscripten_func_i%(eyes)s,
''' % locals()
    print '''
    QEMU_EMSCRIPTEN_FUNC_MAX
} emscripten_func_type;

#define QEMU_EMSCRIPTEN_FUNC_TYPE_BITS %(typebits)d
#define QEMU_EMSCRIPTEN_FUNC_PTR_BITS (8 * sizeof(tcg_target_long) - QEMU_EMSCRIPTEN_FUNC_TYPE_BITS)

static inline tcg_target_long make_emscripten_func_packed(
        tcg_target_long em_ptr, emscripten_func_type type) {
    QEMU_BUILD_BUG_ON((!QEMU_EMSCRIPTEN_FUNC_MAX)
            || (QEMU_EMSCRIPTEN_FUNC_MAX & (QEMU_EMSCRIPTEN_FUNC_MAX - 1)));
    assert(!(type & -QEMU_EMSCRIPTEN_FUNC_MAX));
    assert(!(em_ptr & (QEMU_EMSCRIPTEN_FUNC_MAX - 1)));
    return em_ptr | (type << QEMU_EMSCRIPTEN_FUNC_PTR_BITS);
}

static inline emscripten_func_type get_emscripten_func_type(
        tcg_target_long em_packed) {
    return em_packed >> QEMU_EMSCRIPTEN_FUNC_PTR_BITS;
}

static inline emscripten_func_type make_emscripten_func_type(int has_ret, int nr_eyes) {
	return (!!has_ret) | (nr_eyes << 1);
}

static inline emscripten_func_type get_emscripten_func_ptr(
        tcg_target_long em_packed) {
    return em_packed & (QEMU_EMSCRIPTEN_FUNC_PTR_BITS - 1);
}
#if defined(EMSCRIPTEN)
#define %(name)s_CASE(em_arg_type,ret,func,...) \\
        case emscripten_func_v ## em_arg_type: (func)(__VA_ARGS__); break; \\
        case emscripten_func_i ## em_arg_type: (ret) = (func)(__VA_ARGS__); break;
''' % locals()

    print '''
#define %(name)s_CASE_0(ret,func) \\
    %(name)s_CASE(,(ret),(func))

''' % locals()

    prev_extras = eyes = ''
    for i in xrange(1, maxcall):
        prev_i = i - 1
        eyes += 'i'
        extras = prev_extras + ',(a%d)' % i
        plain_extras = extras.replace('(', '').replace(')', '')
        print '''
#define %(name)s_CASE_%(i)d(%(args)s%(plain_extras)s) \\
    %(name)s_CASE_%(prev_i)d(%(protected_args)s%(prev_extras)s) \\
    %(name)s_CASE(%(eyes)s,%(protected_args)s%(extras)s)
''' % locals()
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

#define %(name)s(func,...) \\
        switch (get_emscripten_func_type(func)) { %(name)s_CASES(func,__VA_ARGS__) }

#else
#define %(name)s(%(args)s,...) \\
        do { (ret) = (func)(__VA_ARGS__); } while(0)
#endif

#endif
''' % locals()

if __name__ == '__main__':
    main()
