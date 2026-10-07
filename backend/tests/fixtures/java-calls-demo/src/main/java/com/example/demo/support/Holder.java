package com.example.demo.support;

public class Holder<T> {
    private T value;

    public int fingerprint() {
        return value.hashCode();
    }
}
