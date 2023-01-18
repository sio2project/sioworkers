import java.lang.System;
public class time_verylong {
    static public void main(String[] args) {
        int i = 2;
        int j = i;

        // runtime (wall time) on various machines:
        // * my workstation (Ryzen 9 5900X): ~0.5s
        // * a dedicated judging machine (Xeon E5530): ~1.1s
        for(; i < Integer.MAX_VALUE; i++)
            j += i;

        System.out.println(j - 1073741826);
    }
}
