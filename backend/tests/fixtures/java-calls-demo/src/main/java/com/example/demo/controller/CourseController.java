package com.example.demo.controller;

import com.example.demo.model.Course;
import com.example.demo.service.CourseCatalog;
import com.example.demo.service.CourseService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/courses")
public class CourseController {
    private final CourseService courseService;
    private final CourseCatalog catalog;

    public CourseController(CourseService courseService, CourseCatalog catalog) {
        this.courseService = courseService;
        this.catalog = catalog;
    }

    @GetMapping
    public List<Course> getCourses() {
        catalog.refresh();
        catalog.refresh();
        return courseService.getCourses();
    }

    @PostMapping
    public Course register(@RequestBody String title) {
        catalog.label(title);
        String name = title.trim();
        audit();
        return this.courseService.register(name);
    }

    @GetMapping("/titles")
    public List<String> titles() {
        Runnable reload = () -> catalog.refresh();
        reload.run();
        return catalog.titles();
    }

    private void audit() {
    }
}
