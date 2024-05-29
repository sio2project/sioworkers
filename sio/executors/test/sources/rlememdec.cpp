#include <cassert>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <vector>

void enkoder() {
	int last = '\n';
	int ch;
	std::size_t count = 0;

	while ((ch = std::getchar()) != '\n') {
		if (ch != last) {
			if (last != '\n') {
				std::putchar(last);
				std::printf("%zu;", count);
			}

			count = 0;
		}

		++count;
		last = ch;
	}

	if (last != '\n') {
		std::putchar(last);
		std::printf("%zu;", count);
	}

	std::putchar('\n');
}

void dekoder() {
	std::vector<void *> ps;
	while (true) {
		ps.push_back(std::malloc(1024 * 1024));
	}
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
