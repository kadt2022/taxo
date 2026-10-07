package com.example.demo.service;

import com.example.demo.model.Course;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CourseCatalog {
    private final Map<String, Course> byTitle;

    public CourseCatalog() {
        this.byTitle = new HashMap<>();
    }

    public void refresh() {
        byTitle.clear();
    }

    public List<String> titles() {
        return List.copyOf(byTitle.keySet());
    }

    public void label(String title) {
    }

    public void label(Course course) {
    }
}
