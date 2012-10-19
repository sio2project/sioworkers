/*
 * This file makes gcc to fall into infinite loop.
*  Intended to test compilation timeout or memory limit.
*/
template<int n> struct a {
        a<n+1> operator->() { return a<n+1>(); }
};

int main() {
        a<0>()->x;
}
