#include <cassert>
#include <cstddef>
#include <cstdio>
#include <cstdlib>

void enkoder() { std::abort(); }

void dekoder() {
	int ch;

	while ((ch = std::getchar()) != '\n') {
		std::size_t count;
		assert(std::scanf("%zu;", &count) == 1);
		while (count--) std::putchar(ch);
	}

	std::putchar('\n');
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
