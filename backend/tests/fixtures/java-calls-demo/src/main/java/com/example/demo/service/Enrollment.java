package com.example.demo.service;

import com.example.demo.model.Course;
import java.util.List;

public class Enrollment {
    private Course course;

    public String describe(Course course) {
        return course.getTitle();
    }

    public int enroll(List<Course> courses) {
        for (Course course : courses) {
            course.getTitle();
        }
        for (Course course : courses) {
            course.getTitle();
        }
        Course first = new Course("Java");
        first.getTitle();
        var again = first;
        again.getTitle();
        course.getTitle();
        return courses.size();
    }

    public int row(Seat seat) {
        return seat.row();
    }
}
