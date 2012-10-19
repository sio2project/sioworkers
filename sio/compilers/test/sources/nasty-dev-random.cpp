/*
 * This test includes /dev/random which would hang gcc.
 * Moreover, as this device is blocking, gcc would consume no cpu_time.
 * So it's testing real_time hard limit.
 * It should be unaccessible in sandboxes.
 */

#include "/dev/random"
