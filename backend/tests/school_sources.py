"""Le depot de reference du recit TAXO-MINIA-ENQUETE-01 (§ 5) : l'inscription a un cours, en couches Java.

`EnrollmentController.enroll` appelle `EnrollmentService.enroll`, qui appelle trois methodes : la recherche de
l'etudiant, celle du cours et l'enregistrement ; les deux recherches appellent chacune leur repository.
"""
PACKAGE = 'com.example.school'


def _type(layer, name, body, imports=()):
    lines = [f'package {PACKAGE}.{layer};', '']
    lines += [f'import {PACKAGE}.{item};' for item in imports]
    lines += ['', f'public class {name} {{', body, '}', '']
    return f'src/main/java/com/example/school/{layer}/{name}.java', '\n'.join(lines)


def _repository(name):
    return _type('repository', name, '    public String findById(String id) {\n        return id;\n    }\n\n'
                                     '    public String save(String value) {\n        return value;\n    }')


def _service(name, repository, method):
    return _type('service', name, f'    private final {repository} repository;\n\n'
                                  f'    public {name}({repository} repository) {{\n'
                                  '        this.repository = repository;\n    }\n\n'
                                  f'    public String {method}(String id) {{\n'
                                  '        return repository.findById(id);\n    }', (f'repository.{repository}',))


def files():
    sources = [
        _repository('StudentRepository'), _repository('CourseRepository'), _repository('EnrollmentRepository'),
        _service('StudentService', 'StudentRepository', 'findStudent'),
        _service('CourseService', 'CourseRepository', 'findCourse'),
        _type('service', 'EnrollmentService',
              '    private final StudentService students;\n    private final CourseService courses;\n'
              '    private final EnrollmentRepository enrollments;\n\n'
              '    public EnrollmentService(StudentService students, CourseService courses, '
              'EnrollmentRepository enrollments) {\n'
              '        this.students = students;\n        this.courses = courses;\n'
              '        this.enrollments = enrollments;\n    }\n\n'
              '    public String enroll(String student, String course) {\n'
              '        String found = students.findStudent(student);\n'
              '        String chosen = courses.findCourse(course);\n'
              '        return enrollments.save(found + chosen);\n    }',
              ('repository.EnrollmentRepository',)),
        _type('controller', 'EnrollmentController',
              '    private final EnrollmentService service;\n\n'
              '    public EnrollmentController(EnrollmentService service) {\n        this.service = service;\n    }\n\n'
              '    public String enroll(String student, String course) {\n'
              '        return service.enroll(student, course);\n    }', ('service.EnrollmentService',)),
    ]
    return dict(sources)


def method(layer, owner, name, parameters):
    return f'symbol:java:{PACKAGE}.{layer}.{owner}#{name}({parameters})'


CONTROLLER = method('controller', 'EnrollmentController', 'enroll', 'String,String')
SERVICE = method('service', 'EnrollmentService', 'enroll', 'String,String')
FIND_STUDENT = method('service', 'StudentService', 'findStudent', 'String')
FIND_COURSE = method('service', 'CourseService', 'findCourse', 'String')
SAVE = method('repository', 'EnrollmentRepository', 'save', 'String')
STUDENT_BY_ID = method('repository', 'StudentRepository', 'findById', 'String')
COURSE_BY_ID = method('repository', 'CourseRepository', 'findById', 'String')
