package org.learn.domain.product;

import com.fasterxml.jackson.annotation.*;
import lombok.Data;

import java.util.List;

@Data
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        visible = true,
        property = "category",
        defaultImpl = BaseSpec.class
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = ElectronicsSpec.class, name = "electronics"),
        @JsonSubTypes.Type(value = HomeSpec.class, name = "home"),
        @JsonSubTypes.Type(value = OutdoorSpec.class, name = "outdoor"),
        @JsonSubTypes.Type(value = ClothingSpec.class, name = "clothing"),
        @JsonSubTypes.Type(value = BookSpec.class, name = "books")

})
@JsonIgnoreProperties(value = { "category" })
public sealed class BaseSpec permits BookSpec, ClothingSpec, ElectronicsSpec, HomeSpec, OutdoorSpec {
    @JsonProperty("weight_kg")
    String weight;
    String material;
    @JsonProperty("origin_country")
    String originCountry;
    @JsonProperty("release_year")
    String releaseYear;
    List<String> certifications;
}

@Data
@JsonIgnoreProperties(value = {"certifications", "category"})
final class ClothingSpec extends BaseSpec {
    String size;
    String color;
    @JsonProperty("care_instructions")
    String careInstructions;
    String gender;
}

@Data
final class ElectronicsSpec extends BaseSpec {
    @JsonProperty("battery_life_hr")
    String batteryLifeHr;
    List<String> connectivity;
    @JsonProperty("storage_gb")
    String storage;
    @JsonProperty("screen_size_inch")
    String screenSize;
    @JsonProperty("warranty_years")
    String warranty;
}

@Data
final class BookSpec extends BaseSpec {
    String isbn;
    int pages;
    String language;
    String publisher;
    String format;
}

@Data
final class HomeSpec extends BaseSpec {
    @JsonProperty("power_watts")
    String powerWatts;
    @JsonProperty("capacity_liters")
    String capacity;
    @JsonProperty("assembly_required")
    boolean assemblyRequired;
    @JsonProperty("dimensions_cm")
    Dimensions dimensions;
}

@Data
final class OutdoorSpec extends BaseSpec {
    @JsonProperty("waterproof_rating")
    String waterProofRating;
    @JsonProperty("temperature_rating_c")
    String temperatureRating;
    @JsonProperty("packed_dimensions_cm")
    Dimensions dimensions;
    @JsonProperty("load_capacity_kg")
    int loadCapacity;
}