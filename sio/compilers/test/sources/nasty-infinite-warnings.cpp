/*
*   Program that counts something using C++ templates.
*   Because of overflow it produces unlimited spam of warnings.
*   Intended to test limit of produced warnings,
*   memory limit and compilation timeout.
*/

#include <cstdio>

template<int I, int D> struct P
{
    enum { V = (
                    D*D == I
                || ( I > 1 && P<I-1, D>::V)
                || ( D>1 && P<I, D-1>::V)
               ) ? 1 : 0};
};

template<> struct P<1, 1>
{
    enum { V = 0 } ;
};

int main()
{
    printf("%d\n", P<12345678, 12345678>::V);
}
