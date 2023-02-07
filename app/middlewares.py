"""
Copyright 2023 DigitME2

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import time


class RequestTimeMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    def __call__(self, environ, start_response):
        start = time.time()
        response = self.app(environ, start_response)
        end = time.time() - start
        if self.app.logger:
            self.app.logger.debug(f"{environ.get('PATH_INFO')} processed in {end} s")
        return response
