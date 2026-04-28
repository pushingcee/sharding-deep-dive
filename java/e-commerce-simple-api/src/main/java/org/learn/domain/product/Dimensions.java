package org.learn.domain.product;

import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
public class Dimensions {
    String width;
    String height;
    String depth;
}
