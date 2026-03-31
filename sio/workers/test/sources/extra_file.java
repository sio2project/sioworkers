import java.nio.file.Files;
import java.nio.file.Paths;

public class extra_file {
    public static void main(String[] args) {
        try {
            byte[] encoded = Files.readAllBytes(Paths.get("./extra_exec_file"));
            String content = new String(encoded);

            if ("DEADBEEF".equals(content.trim())) {
                System.exit(0);
            } else {
                System.exit(1);
            }
        } catch (Exception e) {
            System.exit(2);
        }
    }
}
