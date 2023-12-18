#include <cassert>
#include <cstddef>
#include <cstdio>

void enkoder() {
	while (true) {}
}

void dekoder() {
}

// rlelib.cpp
//
#include <cassert>
#include <cstdio>

extern void dekoder();
extern void enkoder();

int main() {
	int ch = std::getchar();

	assert(ch == 'D' || ch == 'E');
	assert(std::getchar() == '\n');

	(ch == 'D' ? dekoder : enkoder)();
}
