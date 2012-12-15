/* This file tests STL features.
   Namely it checks if libstdc++ with RBtree rotations is available.
*/
#include <iostream>
#include <sstream>
#include <set>
using namespace std;
bool op, f=1;
int cost, n;

int main(int argc, char** argv)
{
    multiset<int> s;
    multiset<int>::iterator it;
    ios_base::sync_with_stdio(0);

    stringstream str("12 1 3 1 5 1 7 0 0 1 4 0 1 9 1 10 0 0 0");

    str >> n;
    while(n)
    {
        str >> op;
        if (op)
        {
            str >> cost;
            s.insert(cost);
            if (!f && cost<*it)
                --it;
        }
        else
        {
            if(f) {
                it=s.begin();
                f=0;
            }
            else
                ++it;
            cout << *it <<endl;
        }
        --n;
    }

    return 0;
}
