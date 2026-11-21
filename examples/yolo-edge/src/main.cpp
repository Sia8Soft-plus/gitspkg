#include <opencv2/core.hpp>
#include <opencv2/dnn.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "Usage: yolo_edge model.onnx input.jpg output.jpg\n";
        return 2;
    }
    try {
        constexpr int size = 640;
        constexpr float confidence = 0.25f;
        cv::Mat image = cv::imread(argv[2]);
        if (image.empty()) throw std::runtime_error("Cannot read input image");

        const double scale = std::min(double(size) / image.cols, double(size) / image.rows);
        const int width = std::max(1, int(std::round(image.cols * scale)));
        const int height = std::max(1, int(std::round(image.rows * scale)));
        const int left = (size - width) / 2;
        const int top = (size - height) / 2;
        cv::Mat resized, padded(size, size, CV_8UC3, cv::Scalar(114, 114, 114));
        cv::resize(image, resized, cv::Size(width, height));
        resized.copyTo(padded(cv::Rect(left, top, width, height)));

        cv::dnn::Net net = cv::dnn::readNetFromONNX(argv[1]);
        net.setPreferableBackend(cv::dnn::DNN_BACKEND_OPENCV);
        net.setPreferableTarget(cv::dnn::DNN_TARGET_CPU);
        net.setInput(cv::dnn::blobFromImage(padded, 1.0 / 255.0,
            cv::Size(size, size), cv::Scalar(), true, false));
        std::vector<cv::Mat> outputs;
        net.forward(outputs, net.getUnconnectedOutLayersNames());
        if (outputs.size() != 1 || outputs[0].dims != 3 ||
            outputs[0].size[0] != 1 || outputs[0].type() != CV_32F) {
            throw std::runtime_error("Expected one float32 [1,4+C,N] or [1,N,4+C] output");
        }

        // Raw detection heads have far more predictions than class attributes.
        const cv::Mat& output = outputs[0];
        const bool channels_first = output.size[1] < output.size[2];
        const int attributes = channels_first ? output.size[1] : output.size[2];
        if (attributes < 5 || attributes > 1024) {
            throw std::runtime_error("Unsupported class count or output layout");
        }
        cv::Mat predictions;
        if (channels_first) {
            cv::Mat raw(attributes, output.size[2], CV_32F, output.data);
            cv::transpose(raw, predictions);
        } else {
            predictions = output.reshape(1, output.size[1]);
        }

        std::vector<cv::Rect> boxes;
        std::vector<float> scores;
        std::vector<int> classes;
        for (int i = 0; i < predictions.rows; ++i) {
            const float* row = predictions.ptr<float>(i);
            bool finite = true;
            for (int j = 0; j < attributes; ++j) finite = finite && std::isfinite(row[j]);
            if (!finite || row[2] <= 0 || row[3] <= 0) continue;
            const float* best = std::max_element(row + 4, row + attributes);
            if (*best < confidence) continue;
            const float x1 = (row[0] - row[2] / 2 - left) / float(scale);
            const float y1 = (row[1] - row[3] / 2 - top) / float(scale);
            const float x2 = (row[0] + row[2] / 2 - left) / float(scale);
            const float y2 = (row[1] + row[3] / 2 - top) / float(scale);
            const int x = int(std::clamp(x1, 0.0f, float(image.cols)));
            const int y = int(std::clamp(y1, 0.0f, float(image.rows)));
            const int right = int(std::clamp(x2, 0.0f, float(image.cols)));
            const int bottom = int(std::clamp(y2, 0.0f, float(image.rows)));
            if (right <= x || bottom <= y) continue;
            boxes.emplace_back(x, y, right - x, bottom - y);
            scores.push_back(*best);
            classes.push_back(int(best - row - 4));
        }

        int detections = 0;
        // Per-class NMS keeps overlapping objects of different classes.
        for (int cls = 0; cls < attributes - 4; ++cls) {
            std::vector<cv::Rect> class_boxes;
            std::vector<float> class_scores;
            std::vector<int> indices;
            for (size_t i = 0; i < boxes.size(); ++i) {
                if (classes[i] == cls) {
                    class_boxes.push_back(boxes[i]);
                    class_scores.push_back(scores[i]);
                }
            }
            cv::dnn::NMSBoxes(class_boxes, class_scores, confidence, 0.45f, indices);
            for (int i : indices) {
                ++detections;
                const std::string label = "class=" + std::to_string(cls) +
                    " score=" + std::to_string(class_scores[i]);
                cv::rectangle(image, class_boxes[i], cv::Scalar(40, 190, 60), 2);
                cv::putText(image, label, class_boxes[i].tl(), cv::FONT_HERSHEY_SIMPLEX,
                    0.5, cv::Scalar(30, 30, 230), 1);
                std::cout << label << "\n";
            }
        }
        const std::filesystem::path output_path(argv[3]);
        if (output_path.has_parent_path()) std::filesystem::create_directories(output_path.parent_path());
        if (!cv::imwrite(output_path.string(), image)) throw std::runtime_error("Cannot write output image");
        std::cout << "detections=" << detections << " output=" << output_path.string() << "\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Inference failed: " << error.what() << "\n";
        return 1;
    }
}
