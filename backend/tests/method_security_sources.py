"""Un petit projet Spring synthetique, securise par une regle d'URL et par la securite de methode.

La verite est etablie a la main sur ces sources : `GET /api/items` exige une authentification par la regle
`/api/**` (ligne 21 de SecurityConfig), et `@PreAuthorize` restreint en plus la methode aux roles ADMIN et
EDITOR (ligne 14 d'ItemController). `@EnableMethodSecurity` (ligne 13) l'active ; CSRF est desactive (ligne 19).
"""

BUILD = """plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
}
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
"""

APPLICATION = """package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
"""

SECURITY = """package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Regles d'URL et securite de methode.
 */
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .csrf(csrf -> csrf.disable())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().permitAll())
                .build();
    }
}
"""

CONTROLLER = """package com.example.shop.web;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    @GetMapping
    @PreAuthorize("hasAnyRole('ADMIN','EDITOR')")
    public List<String> items() {
        return List.of();
    }
}
"""

FILES = {
    'build.gradle': BUILD,
    'src/main/java/com/example/shop/ShopApplication.java': APPLICATION,
    'src/main/java/com/example/shop/config/SecurityConfig.java': SECURITY,
    'src/main/java/com/example/shop/web/ItemController.java': CONTROLLER,
}
