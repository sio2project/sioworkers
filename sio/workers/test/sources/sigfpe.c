int main() {
    volatile int zero = 0; // To prevent the compilator from optimizing this out.
    // Otherwise it can result in SIGILL.
    return 4 / zero;
}
