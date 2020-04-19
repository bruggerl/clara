import java.util.*;

public class Main {
    public List<Double> computeDeriv(List<Double> input) {
        int i = 1;
        List<Double> result = new ArrayList<>();

        for (int i = 1; i < input.size(); i++) {
            result.add(input.get(i)*i);
        }

        if (result.isEmpty()) {
            result.add(0.0);
        }

        return result;
    }
}